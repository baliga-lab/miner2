import datetime,numpy,pandas,time,sys
import sklearn,sklearn.decomposition
import multiprocessing, multiprocessing.pool
from collections import Counter

def cluster(expression_data, min_number_genes=6,
            min_number_overexp_samples=4,
            max_samples_excluded=0.50,
            random_state=12,
            overexpression_threshold=80,
            num_cores=1):
    """
    Create a list of initial clusters. This is a list of list of gene names
    """

    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S \t coexpression"))

    df = expression_data.copy()

    max_step = int(numpy.round(10 * max_samples_excluded))
    all_genes_mapped = []
    best_hits = []

    zero = numpy.percentile(expression_data, 0)
    expression_threshold = numpy.mean([numpy.percentile(expression_data.iloc[:,i][expression_data.iloc[:,i] > zero], overexpression_threshold) for i in range(expression_data.shape[1])])

    trial = -1

    for step in range(max_step):
        print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S \t working on coexpression step {} out of {}".format(step + 1, max_step)))
        trial += 1
        genes_mapped = []
        best_mapped = []

        pca = sklearn.decomposition.PCA(10, random_state=random_state)
        principal_components = pca.fit_transform(df.T)
        principal_df = pandas.DataFrame(principal_components)
        principal_df.index = df.columns

        # explore PCs in parallel
        pcs = numpy.arange(10)
        tasks = [(df, principal_df, element, min_number_genes) for element in pcs]
        hydra = multiprocessing.pool.Pool(num_cores)
        genes_mapped_parallel = hydra.map(gene_mapper, tasks)
        for element in genes_mapped_parallel:
            for gene in element:
                genes_mapped.append(gene)

        all_genes_mapped.extend(genes_mapped)

        try:
            stackGenes = numpy.hstack(genes_mapped)
        except:
            stackGenes = []

        residual_genes = list(set(df.index) - set(stackGenes))
        df = df.loc[residual_genes, :]

        # significance surrogate in parallel
        tasks = [(element, expression_data, expression_threshold)
                 for element in genes_mapped]
        parallel_hits = hydra.map(parallel_overexpress_surrogate, tasks)

        for element, hits in parallel_hits:
            best_mapped.append(hits)
            if len(hits) > min_number_overexp_samples:
                best_hits.append(element)

        if len(best_mapped) > 0:
            count_hits = Counter(numpy.hstack(best_mapped))
            ranked = count_hits.most_common()
            dominant = [i[0] for i in ranked[0:int(numpy.ceil(0.1 * len(ranked)))]]
            remainder = [i for i in numpy.arange(df.shape[1]) if i not in dominant]
            df = df.iloc[:, remainder]

    best_hits.sort(key=lambda s: -len(s))
    return best_hits

def combineClusters(axes,clusters,threshold=0.925):
    combineAxes = {}
    filterKeys = numpy.array(list(axes.keys())) # ALO: changed to list because of Py3
    axesMatrix = numpy.vstack([axes[i] for i in filterKeys])
    for key in filterKeys:
        axis = axes[key]
        pearson = pearson_array(axesMatrix,axis)
        combine = numpy.where(pearson>threshold)[0]
        combineAxes[key] = filterKeys[combine]

    revisedClusters = {}
    combinedKeys = decomposeDictionaryToLists(combineAxes)
    for keyList in combinedKeys:
        genes = list(set(numpy.hstack([clusters[i] for i in keyList])))
        revisedClusters[len(revisedClusters)] = genes

    return revisedClusters

def decompose(geneset,expressionData,minNumberGenes=6):
    fm = FrequencyMatrix(expressionData.loc[geneset,:])
    tst = numpy.multiply(fm,fm.T)
    tst[tst<numpy.percentile(tst,80)]=0
    tst[tst>0]=1
    unmix_tst = unmix(tst)
    unmixedFiltered = [i for i in unmix_tst if len(i)>=minNumberGenes]
    return unmixedFiltered

def decomposeDictionaryToLists(dict_):
    decomposedSets = []
    for key in dict_.keys():
        newSet = iterativeCombination(dict_,key,iterations=25)
        if newSet not in decomposedSets:
            decomposedSets.append(newSet)
    return decomposedSets

def FrequencyMatrix(matrix,overExpThreshold = 1):
    
    numRows = matrix.shape[0]
    
    if type(matrix) == pandas.core.frame.DataFrame:
        index = matrix.index
        matrix = numpy.array(matrix)
    else:
        index = numpy.arange(numRows)
    
    matrix[matrix<overExpThreshold] = 0
    matrix[matrix>0] = 1
            
    hitsMatrix = pandas.DataFrame(numpy.zeros((numRows,numRows)))
    for column in range(matrix.shape[1]):
        geneset = matrix[:,column]
        hits = numpy.where(geneset>0)[0]
        hitsMatrix.iloc[hits,hits] += 1
        
    frequencyMatrix = numpy.array(hitsMatrix)
    traceFM = numpy.array([frequencyMatrix[i,i] for i in range(frequencyMatrix.shape[0])]).astype(float)
    if numpy.count_nonzero(traceFM)<len(traceFM):
        #subset nonzero. computefm. normFM zeros with input shape[0]. overwrite by slice np.where trace>0
        nonzeroGenes = numpy.where(traceFM>0)[0]
        normFMnonzero = numpy.transpose(numpy.transpose(frequencyMatrix[nonzeroGenes,:][:,nonzeroGenes])/traceFM[nonzeroGenes])
        normDf = pandas.DataFrame(normFMnonzero)
        normDf.index = index[nonzeroGenes]
        normDf.columns = index[nonzeroGenes]          
    else:            
        normFM = numpy.transpose(numpy.transpose(frequencyMatrix)/traceFM)
        normDf = pandas.DataFrame(normFM)
        normDf.index = index
        normDf.columns = index   
    
    return normDf

def getAxes(clusters,expressionData):
    axes = {}
    for key in clusters.keys():
        genes = clusters[key]
        fpc = sklearn.decomposition.PCA(1)
        principalComponents = fpc.fit_transform(expressionData.loc[genes,:].T)
        axes[key] = principalComponents.ravel()
    return axes

def gene_mapper(task):
    genes_mapped = []
    df, principal_df, i, min_number_genes = task
    pearson = pearson_array(numpy.array(df), numpy.array(principal_df[i]))
    highpass = max(numpy.percentile(pearson,95), 0.1)
    lowpass = min(numpy.percentile(pearson,5), -0.1)
    cluster1 = numpy.array(df.index[numpy.where(pearson > highpass)[0]])
    cluster2 = numpy.array(df.index[numpy.where(pearson < lowpass)[0]])

    for clst in [cluster1, cluster2]:
        pdc = recursiveAlignment(clst, expressionData=df, minNumberGenes=min_number_genes)
        if len(pdc) == 0:
            continue
        elif len(pdc) == 1:
            genes_mapped.append(pdc[0])
        elif len(pdc) > 1:
            for j in range(len(pdc)-1):
                if len(pdc[j]) > min_number_genes:
                    genes_mapped.append(pdc[j])

    return genes_mapped

def iterativeCombination(dict_,key,iterations=25):
    initial = dict_[key]
    initialLength = len(initial)
    for iteration in range(iterations):
        revised = [i for i in initial]
        for element in initial:
            revised = list(set(revised)|set(dict_[element]))
        revisedLength = len(revised)
        if revisedLength == initialLength:
            return revised
        elif revisedLength > initialLength:
            initial = [i for i in revised]
            initialLength = len(initial)
    return revised

def parallel_overexpress_surrogate(task):
    element, expression_data, expression_threshold = task

    tmp_cluster = expression_data.loc[element, :]
    tmp_cluster[tmp_cluster < expression_threshold] = 0
    tmp_cluster[tmp_cluster > 0] = 1
    sum_cluster = numpy.array(numpy.sum(tmp_cluster, axis=0))
    hits = numpy.where(sum_cluster > 0.333 * len(element))[0]

    return (element, hits)


def pearson_array(array,vector):
    ybar = numpy.mean(vector)
    sy = numpy.std(vector,ddof=1)
    yterms = (vector-ybar)/float(sy)

    array_sx = numpy.std(array,axis=1,ddof=1)

    if 0 in array_sx:
        passIndex = numpy.where(array_sx>0)[0]
        array = array[passIndex,:]
        array_sx = array_sx[passIndex]

    array_xbar = numpy.mean(array, axis=1)
    product_array = numpy.zeros(array.shape)

    for i in range(0,product_array.shape[1]):
        product_array[:,i] = yterms[i]*(array[:,i] - array_xbar)/array_sx

    return numpy.sum(product_array,axis=1)/float(product_array.shape[1]-1)


def processCoexpressionLists(lists,expressionData,threshold=0.925):
    reconstructed = reconstruction(lists,expressionData,threshold)
    reconstructedList = [reconstructed[i] for i in reconstructed.keys()]
    reconstructedList.sort(key = lambda s: -len(s))
    return reconstructedList

def reconstruction(decomposedList,expressionData,threshold=0.925):
    clusters = {i:decomposedList[i] for i in range(len(decomposedList))}
    axes = getAxes(clusters,expressionData)
    recombine = combineClusters(axes,clusters,threshold)
    return recombine

def recursiveAlignment(geneset,expressionData,minNumberGenes=6):
    recDecomp = recursiveDecomposition(geneset,expressionData,minNumberGenes)
    if len(recDecomp) == 0:
        return []
    reconstructed = reconstruction(recDecomp,expressionData)
    reconstructedList = [reconstructed[i] for i in list(reconstructed.keys()) if len(reconstructed[i])>minNumberGenes] # ALO: changed to list becasue of Py3
    reconstructedList.sort(key = lambda s: -len(s))
    return reconstructedList

def recursiveDecomposition(geneset,expressionData,minNumberGenes=6):
    unmixedFiltered = decompose(geneset,expressionData,minNumberGenes=minNumberGenes)
    if len(unmixedFiltered) == 0:
        return []
    shortSets = [i for i in unmixedFiltered if len(i)<50]
    longSets = [i for i in unmixedFiltered if len(i)>=50]    
    if len(longSets)==0:
        return unmixedFiltered
    for ls in longSets:
        unmixedFiltered = decompose(ls,expressionData,minNumberGenes=minNumberGenes)
        if len(unmixedFiltered)==0:
            continue
        shortSets.extend(unmixedFiltered)
    return shortSets

def reviseInitialClusters(clusterList,expressionData,threshold=0.925):
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S \t genes clustered: {}".format(len(set(numpy.hstack(clusterList))))))
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S \t revising initial clusters"))
    coexpressionLists = processCoexpressionLists(clusterList,expressionData,threshold)
    coexpressionLists.sort(key= lambda s: -len(s))
    
    for iteration in range(5):
        previousLength = len(coexpressionLists)
        coexpressionLists = processCoexpressionLists(coexpressionLists,expressionData,threshold)
        newLength = len(coexpressionLists)
        if newLength == previousLength:
            break
    
    coexpressionLists.sort(key= lambda s: -len(s))
    coexpressionDict = {str(i):list(coexpressionLists[i]) for i in range(len(coexpressionLists))}

    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S \t revision completed"))
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S \t genes clustered: {}".format(len(set(numpy.hstack(clusterList))))))
    print(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S \t unique clusters: {}".format(len(coexpressionDict))))

    return coexpressionDict

def unmix(df,iterations=25,returnAll=False):    
    frequencyClusters = []
    for iteration in range(iterations):
        sumDf1 = df.sum(axis=1)

        # ALO: consistent return in case of ties
        selected=sumDf1[sumDf1.values == sumDf1.values.max()]
        chosen=selected.index.tolist()
        if len(chosen) > 1:
            chosen.sort()
        maxSum=chosen[0]
        # end ALO
                  
        hits = numpy.where(df.loc[maxSum]>0)[0]
        hitIndex = list(df.index[hits])
        block = df.loc[hitIndex,hitIndex]
        blockSum = block.sum(axis=1)
        coreBlock = list(blockSum.index[numpy.where(blockSum>=numpy.median(blockSum))[0]])
        remainder = list(set(df.index)-set(coreBlock))
        frequencyClusters.append(coreBlock)
        if len(remainder)==0:
            return frequencyClusters
        if len(coreBlock)==1:
            return frequencyClusters
        df = df.loc[remainder,remainder]
    if returnAll is True:
        frequencyClusters.append(remainder)
    
    return frequencyClusters

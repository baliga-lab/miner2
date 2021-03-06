#!/usr/bin/env python3
import sys
import unittest

import pandas as pd
import numpy as np
import logging
import json
import os
from collections import defaultdict

from miner2 import mechanistic_inference as mechinf, preprocess

MIN_REGULON_GENES = 5

class MechinfTest(unittest.TestCase):

    def compare_dicts(self, d1, d2):
        """compare 1-level deep dictionary"""
        ref_keys = sorted(d1.keys())
        keys = sorted(d2.keys())
        self.assertEquals(ref_keys, keys)

        for key in keys:
            ref_genes = sorted(d1[key])
            genes = sorted(d2[key])
            if len(ref_genes) != len(genes):
                print("MISMATCH KEY: '%s'" % key)
                print('REF GENES')
                print(ref_genes)
                print('GENES')
                print(genes)
            self.assertEquals(ref_genes, genes)

    def compare_dicts2(self, d1, d2):
        """compare 2-level deep dictionary"""
        ref_keys = sorted(d1.keys())
        keys = sorted(d2.keys())
        self.assertEquals(ref_keys, keys)

        for key1 in keys:
            # note that the keys from the JSON file has string-values integers as keys
            # while the keys2 are integer keys !!! This is regardless whether Python2 or 3
            ref_keys2 = sorted(map(int, d1[key1].keys()))
            keys2 = sorted(d2[key1].keys())
            self.assertEquals(ref_keys2, keys2)

            # compare gene lists on the second level
            for key2 in keys2:
                ref_genes = sorted(d1[key1][str(key2)])  # note that the ref dict contains string keys
                genes = sorted(d2[key1][key2])
                self.assertEquals(ref_genes, genes)

    def test_get_coexpression_modules(self):
        # test data was generated with the Python 2 version
        with open('testdata/mechanisticOutput-001.json') as infile:
            mechout = json.load(infile)
        with open('testdata/coexpressionModules-001.json') as infile:
            ref_coexp_mods = json.load(infile)
        coexp_mods = mechinf.get_coexpression_modules(mechout)
        self.compare_dicts(ref_coexp_mods, coexp_mods)

    def test_get_coregulation_modules(self):
        with open('testdata/mechanisticOutput-001.json') as infile:
            mechout = json.load(infile)
        with open('testdata/coregulationModules-001.json') as infile:
            ref_coreg_mods = json.load(infile)

        coreg_mods = mechinf.get_coregulation_modules(mechout)
        self.compare_dicts(ref_coreg_mods, coreg_mods)

    def test_get_regulons(self):
        with open('testdata/ref_regulons-001.json') as infile:
            ref_regulons = json.load(infile)
        with open('testdata/coregulationModules-001.json') as infile:
            coreg_mods = json.load(infile)

        regulons = mechinf.get_regulons(coreg_mods,
                                        min_number_genes=MIN_REGULON_GENES,
                                        freq_threshold=0.333)
        self.compare_dicts2(ref_regulons, regulons)

    def test_coincidence_matrix(self):
        with open('testdata/sub_regulons-001.json') as infile:
            sub_regulons = json.load(infile)
        ref_norm_df = pd.read_csv('testdata/coincidence_matrix-001.csv', index_col=0, header=0)
        norm_df = mechinf.coincidence_matrix(sub_regulons, 0.333)
        self.assertTrue(ref_norm_df.equals(norm_df))

    def test_unmix(self):
        norm_df = pd.read_csv('testdata/coincidence_matrix-001.csv', index_col=0, header=0)
        with open('testdata/unmixed-001.json') as infile:
            ref_unmixed = json.load(infile)
        unmixed = mechinf.unmix(norm_df)
        self.assertEquals(ref_unmixed, unmixed)

    def test_remix(self):
        norm_df = pd.read_csv('testdata/coincidence_matrix-001.csv', index_col=0, header=0)
        with open('testdata/unmixed-001.json') as infile:
            unmixed = json.load(infile)
        with open('testdata/remixed-001.json') as infile:
            ref_remixed = json.load(infile)
        remixed = mechinf.remix(norm_df, unmixed)
        #with open('testdata/remixed-001.json', 'w') as outfile:
        #    json.dump(remixed, outfile)
        self.assertEquals(ref_remixed, remixed)

    def test_get_regulon_dictionary(self):
        with open('testdata/ref_regulons-001.json') as infile:
            regulons = json.load(infile)
        with open('testdata/ref_regulon_modules-001.json') as infile:
            ref_regulon_modules = json.load(infile)
        ref_regulon_df = pd.read_csv('testdata/ref_regulon_df-001.csv', index_col=0, header=0)

        regulon_modules, regulon_df = mechinf.get_regulon_dictionary(regulons)
        # careful ! Regulon_ID comes out as text in regulon_df, but is
        # integer in ref_regulon_df !!!
        regulon_df['Regulon_ID'] = pd.to_numeric(regulon_df['Regulon_ID'])
        self.assertTrue(ref_regulon_df.equals(regulon_df))
        self.assertEquals(ref_regulon_modules, regulon_modules)

    def test_convert_dictionary(self):
        with open('testdata/coexpressionDictionary-001.json') as infile:
            revised_clusters = json.load(infile)

        conv_table = pd.read_csv('testdata/ref_convtable-001.csv', header=0, index_col=0,
                                 squeeze=True)

        with open('testdata/ref_annot_rev_clusters-001.json') as infile:
            ref_annot_rev_clusters = json.load(infile)

        annot_rev_clusters = mechinf.convert_dictionary(revised_clusters,
                                                        conv_table)
        self.compare_dicts(ref_annot_rev_clusters, annot_rev_clusters)

    def test_convert_regulons(self):
        conv_table = pd.read_csv('testdata/ref_convtable-001.csv', header=0, index_col=0,
                                 squeeze=True)
        regulon_df = pd.read_csv('testdata/ref_regulon_df-001.csv', index_col=0, header=0)
        ref_regulon_annotated_df = pd.read_csv('testdata/ref_annotated_regulon_df-001.csv',
                                               header=0, index_col=0)

        regulon_annotated_df = mechinf.convert_regulons(regulon_df, conv_table)

        # careful ! Regulon_ID comes out as text in regulon_df, but is
        # integer in ref_regulon_df !!!
        regulon_annotated_df['Regulon_ID'] = pd.to_numeric(regulon_annotated_df['Regulon_ID'])

        #regulon_annotated_df.to_csv("testdata/ref_annotated_regulon_df-001.csv")
        self.assertTrue(ref_regulon_annotated_df.equals(regulon_annotated_df))

    def test_get_principal_df(self):
        exp_data, conv_table = preprocess.main('testdata/ref_exp-000.csv',
                                               'testdata/identifier_mappings.txt')
        with open('testdata/coexpressionDictionary-001.json') as infile:
            revised_clusters = json.load(infile)

        ref_principal_df = pd.read_csv('testdata/ref_principal_df-001.csv', index_col=0, header=0)
        axes = mechinf.get_principal_df(revised_clusters, exp_data,
                                        subkey=None, min_number_genes=1)
        #axes.to_csv('testdata/ref_principal_df-001.csv', header=True, index=True)
        self.assertTrue(np.isclose(ref_principal_df, axes).all())

    def test_enrichment(self):
        exp_data, conv_table = preprocess.main('testdata/ref_exp-000.csv',
                                               'testdata/identifier_mappings.txt')
        with open('testdata/coexpressionDictionary-001.json') as infile:
            revised_clusters = json.load(infile)
        axes = pd.read_csv('testdata/ref_principal_df-001.csv', index_col=0, header=0)
        database_path = os.path.join('miner2/data', "tfbsdb_tf_to_genes.pkl")
        with open('testdata/ref_mechout-001.json') as infile:
            ref_mechout = json.load(infile)

        mechout = mechinf.enrichment(axes, revised_clusters, exp_data,
                                     correlation_threshold=0.2,
                                     num_cores=5,
                                     database_path=database_path)
        #with open('testdata/ref_mechout-001.json', 'w') as outfile:
        #    json.dump(mechout, outfile)
        self.compare_dicts(ref_mechout, mechout)

if __name__ == '__main__':
    SUITE = []
    LOG_FORMAT = '%(asctime)s %(message)s'
    logging.basicConfig(format=LOG_FORMAT, level=logging.DEBUG,
                        datefmt='%Y-%m-%d %H:%M:%S \t')
    SUITE.append(unittest.TestLoader().loadTestsFromTestCase(MechinfTest))
    if len(sys.argv) > 1 and sys.argv[1] == 'xml':
      xmlrunner.XMLTestRunner(output='test-reports').run(unittest.TestSuite(SUITE))
    else:
      unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(SUITE))

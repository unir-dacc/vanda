from ai.summarizer import summary
from ai.tokens import tokenizer
from django.test import TestCase, Client

from web import services

default_snp = "268"
default_snp_pmid = "8541837"
default_snp_title = "A frequently occurring mutation in the lipoprotein lipase gene (Asn291Ser) contributes to the expression of familial combined hyperlipidemia "
default_snp_abstract = "We performed denaturing gradient gel electrophoresis (DGGE) of exons 4, 5, 6 and their exon-intron boundaries of the LPL-gene in 169 unrelated male patients suffering from familial combined hyperlipidemia (FCH). Twenty patients were found to carry a nucleotide substitution in exon 6. Sequence and PCR/digestion analysis revealed one common mutation (Asn291Ser) in all these cases. This mutation was talso present in 215 male controls, albeit at a lower frequency than in FCH patients (10/215 = 4.6% vs. 20/169 = 11.8%; p < 0.02). Analysis of lipid, lipoprotein and apolipoprotein levels demonstrated an association between the presence of this Asn291Ser substitution and decreased HDL-cholesterol (0.94 +/- 0.31 vs. 1.12 +/- 0.26 mmol/l; p < 0.04) in our controls. FCH patients carrying this mutation showed decreased HDL-cholesterol (0.75 +/- 0.16 vs. 0.95 +/- 0.36 mmol/l; p = 0.05) and increased triglyceride levels (5.96 +/- 4.12 vs. 3.48 +/- 1.78 mmol/l; p < 0.005) compared to non-carriers. The high triglyceride and low HDL-cholesterol phenotype in carriers of this substitution was most obvious when BMI exceeded 27 kg/m2. Our study of male FCH patients revealed the presence of a common mutation in the LPL-gene that is associated with lipoprotein abnormalities, indicating that defective LPL is at least one of the factors contributing to the FCH-phenotype. "

default_gene = "BCO1"
default_gene_pmid = "17951468"
default_gene_title = "Loss-of-function mutation in carotenoid 15,15'-monooxygenase identified in a patient with hypercarotenemia and hypovitaminosis A."
default_gene_abstract = "The enzyme carotenoid 15,15'-monooxygenase (CMO1) catalyzes the first step in the conversion of dietary provitamin A carotenoids to vitamin A in the small intestine. Plant carotenoids are an important dietary source of vitamin A (retinol) and the sole source of vitamin A for vegetarians. Vitamin A is essential for normal embryonic development as well as normal physiological functions in children and adults. Here, we describe one heterozygous T170M missense mutation in the CMO1 gene in a subject with hypercarotenemia and mild hypovitaminosis A. The replacement of a highly conserved threonine with methionine results in a 90% reduction in enzyme activity when analyzed in vitro using purified recombinant enzymes. The Michaelis-Menten constant (K(m)) for the mutated enzyme is normal. Ample amounts of carotenoids are present in plasma of persons consuming a normal Western diet, suggesting that the enzyme is saturated with substrate under normal conditions. Therefore, we propose that haploinsufficiency of the CMO1 enzyme may cause symptoms of hypercarotenemia and hypovitaminosis A in individuals consuming a carotenoid-containing and vitamin A-deficient diet."


class ServicesTestCase(TestCase):
    def test_get_abstracts_by_snp(self):
        articles = services.get_abstracts_by_snp(default_snp)

        pmids = []

        for article in articles:
            pmids.append(article['pmid'])

        self.assertIn(default_snp_pmid, pmids)

    def test_get_abstracts_by_gene(self):
        articles, snp_to_pubmed = services.get_abstracts_by_gene(default_gene)

        pmids = []

        for article in articles:
            pmids.append(article['pmid'])

        self.assertIn(default_gene_pmid, pmids)


class ModelsTestCase(TestCase):
    def test_summary_text(self):

        summary_abstract = summary(default_gene_abstract)

        self.assertLess(len(summary_abstract), len(default_gene_abstract))

    def test_tokenize_text(self):
        tokens = tokenizer(default_snp_abstract)

        self.assertGreater(len(tokens), 0)


class ViewTestCase(TestCase):
    def test_snp_page(self):
        client = Client()

        response = client.get('/snp/' + default_snp)
        self.assertEqual(response.status_code, 200)

    def test_gene_page(self):
        client = Client()

        response = client.get('/gene/' + default_gene)
        self.assertEqual(response.status_code, 200)

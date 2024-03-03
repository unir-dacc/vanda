from ai.summarizer import summary
from ai.tokens import tokenize
from django.test import TestCase, Client

from web import services

default_snp = "268"
default_snp_pmid = "8541837"

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
        articles = services.get_abstracts_by_gene(default_gene)

        pmids = []

        for article in articles:
            pmids.append(article['pmid'])

        self.assertIn(default_gene_pmid, pmids)


class ModelsTestCase(TestCase):
    def test_summary_text(self):

        summary_abstract = summary(default_gene_abstract)

        self.assertLess(len(summary_abstract), len(default_gene_abstract))

    def test_tokenize_text(self):

        text = {
            'abstract': default_gene_abstract,
            'pmid': default_gene_pmid,
            'title': default_gene_title
        }

        tokens = tokenize(text)

        self.assertGreater(len(tokens), 0)


class ViewTestCase(TestCase):
    def test_snp_page(self):
        client = Client()

        response = client.get('/' + default_snp)
        self.assertEqual(response.status_code, 200)

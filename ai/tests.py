from django.test import TestCase, Client

from web import services

default_snp = "268"
default_pmid = "8541837"


class ServicesTestCase(TestCase):
    def test_get_abstracts_by_snp(self):
        articles = services.get_abstracts_by_snp(default_snp)

        pmids = []

        for article in articles:
            pmids.append(article['pmid'])

        self.assertIn(default_pmid, pmids)


class ViewTestCase(TestCase):
    def test_snp_abstracts(self):
        client = Client()

        response = client.get('/api/snp/' + default_snp + '/abstracts')
        self.assertEqual(response.status_code, 200)

    def test_gene_abstracts(self):
        client = Client()

        response = client.get('/api/gene/' + default_snp + '/abstracts')
        self.assertEqual(response.status_code, 200)

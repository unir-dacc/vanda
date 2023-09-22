from django.test import TestCase, Client
from django.test.client import resolve
from django.urls import reverse

from . import services

default_snp = "rs268"
snp_response = ['rs268', '8', '19956017', 'A/G', 'LPL']
hgvs_snp_response = ['NC_000008.11:g.19956018=',
                     'NC_000008.11:g.19956018A>G',
                     'NC_000008.10:g.19813529=',
                     'NC_000008.10:g.19813529A>G',
                     'NG_008855.2:g.59302=',
                     'NG_008855.2:g.59302A>G',
                     'NM_000237.3:c.953=',
                     'NM_000237.3:c.953A>G',
                     'NM_000237.2:c.953=',
                     'NM_000237.2:c.953A>G',
                     'NP_000228.1:p.Asn318=',
                     'NP_000228.1:p.Asn318Ser']


snp = services.SnpData(default_snp)


class ServicesTestCase(TestCase):

    def test_get_by_name(self):
        response = services.search_snp(default_snp)

        self.assertListEqual(response[0], snp_response)

    def test_get_snp_hgvs(self):
        self.assertListEqual(snp.get_snp_hgvs(), hgvs_snp_response)


class ViewTestCase(TestCase):

    def test_homepage(self):
        client = Client()

        response = client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_search_parameter(self):
        client = Client()

        response = client.get('/', {"q": default_snp})
        self.assertEqual(response.status_code, 200)

    def test_snp(self):
        client = Client()

        response = client.get('/api/snp/' + default_snp + '/hgvs')
        self.assertEqual(response.status_code, 200)

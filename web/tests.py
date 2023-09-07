from django.test import TestCase, Client
from django.test.client import resolve
from django.urls import reverse

from . import services

default_snp = "rs268"
correct_response = ['rs268', '8', '19956017', 'A/G', 'LPL']


class ServicesTestCase(TestCase):
    def test_get_by_name(self):
        response = services.get_by_name(default_snp)

        self.assertListEqual(response[0], correct_response)


class ViewTestCase(TestCase):
    def test_homepage(self):
        client = Client()

        response = client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_search_parameter(self):
        client = Client()

        response = client.get('/', {"q": default_snp})
        self.assertEqual(response.status_code, 200)

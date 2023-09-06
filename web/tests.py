from django.test import TestCase, Client
from django.test.client import resolve
from django.urls import reverse

from . import services

default_snp = "rs1234500045"
correct_response = [['rs1234500045', '1', '124244964', 'G/A, G/C, G/T', '']]


class ServicesTestCase(TestCase):
    def test_get_by_name(self):
        response = services.get_by_name(default_snp)

        self.assertListEqual(response, correct_response)


class ViewTestCase(TestCase):
    def test_homepage(self):
        client = Client()

        response = client.get('/')
        self.assertEqual(response.status_code, 200)

        response = client.get('/', {"q": default_snp})

        self.assertEqual(response.status_code, 200)

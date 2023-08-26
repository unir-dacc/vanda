import requests

def get_by_name(query):
    url = f"https://clinicaltables.nlm.nih.gov/api/snps/v3/search?terms={query}"
    response = requests.get(url)

    r = []
    if response.status_code == 200:
        r = response.json()
    else:
        print(f"Resonse code: {response.status_code}")

	return r[3]

from transformers import pipeline
from transformers import AutoTokenizer, AutoModelForTokenClassification


tokenizer = AutoTokenizer.from_pretrained("d4data/biomedical-ner-all")
model = AutoModelForTokenClassification.from_pretrained(
    "d4data/biomedical-ner-all")

pipe = pipeline("ner", model=model, tokenizer=tokenizer,
                aggregation_strategy="simple")

characters = [',', '.', '!', '?', ';', '"', "'", " ", '(', ')']

considerable_tokens = ["Disease_disorder", "Sign_symptom", "Medication"]

context = 130


def tokenize(text):
    result = pipe(text['abstract'])

    tokens = []
    words = []

    for item in result:
        if item['entity_group'] in considerable_tokens:
            token = {}
            while text['abstract'][item['start']] not in characters:
                item['start'] -= 1

            while text['abstract'][item['end']] not in characters:
                item['end'] += 1

            word = text['abstract'][item['start'] + 1:item['end']]

            if word not in words:
                token['word'] = word
                token['pmid'] = text['pmid']
                token['title'] = text['title']
                token['abstract'] = text['abstract']
                tokens.append(token)
                words.append(word)

    return tokens

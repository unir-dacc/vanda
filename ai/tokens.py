from transformers import pipeline
from transformers import AutoTokenizer, AutoModelForTokenClassification


tokenizer = AutoTokenizer.from_pretrained("d4data/biomedical-ner-all")
model = AutoModelForTokenClassification.from_pretrained(
    "d4data/biomedical-ner-all")

pipe = pipeline("ner", model=model, tokenizer=tokenizer,
                aggregation_strategy="simple")

characters = [',', '.', '!', '?', ';', '"', "'", " ", '(', ')']

considerable_tokens = ["Disease_disorder"]

context = 130


def is_token_in_considerable_tokens(token):
    return token["entity_group"] in considerable_tokens


def tokenizer(text):
    result = pipe(text)

    words = []

    tokens = list(filter(is_token_in_considerable_tokens, result))

    print(tokens)
    for item in tokens:
        while text[item['start']] not in characters:
            item['start'] -= 1

        while text[item['end']] not in characters:
            item['end'] += 1

        word = text[item['start'] + 1:item['end']].lower()

        if word not in words:
            words.append(word)

    return words

from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification

tokenizer = AutoTokenizer.from_pretrained("d4data/biomedical-ner-all")
model = AutoModelForTokenClassification.from_pretrained("d4data/biomedical-ner-all")

pipe = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy="simple")

characters = [",", ".", "!", "?", ";", '"', "'", " ", "(", ")"]

considerable_tokens = ["Disease_disorder"]


def is_token_in_considerable_tokens(token):
    return token["entity_group"] in considerable_tokens


def extract_diseases(text):
    result = pipe(text)
    tokens = list(filter(is_token_in_considerable_tokens, result))

    words = []
    acronyms = []

    for item in tokens:
        while text[item["start"]] not in characters:
            item["start"] -= 1
        while text[item["end"]] not in characters:
            item["end"] += 1

        word = text[item["start"] + 1 : item["end"]].strip()

        if word.isupper() and len(word) <= 6:
            acronyms.append(word)
        else:
            words.append(word)

    if not words:
        return acronyms

    return words

from collections import defaultdict
from itertools import combinations
from app import tokenizer

from app.summary import summary


def render_topics(articles):
    for item in articles:
        item["tokens"] = tokenizer.extract_diseases(item["abstract"])

    topics = defaultdict(list)

    for article in articles:
        for token in article["tokens"]:
            topics[token].append(
                {
                    "pmid": article["pmid"],
                    "title": article["title"],
                    "abstract": summary(article["abstract"]),
                }
            )

    grouped_topics = {}
    unique_sets = {}

    for key, articles_list in topics.items():
        articles_tuple = tuple(sorted(article["pmid"] for article in articles_list))

        if articles_tuple in unique_sets:
            grouped_topics[unique_sets[articles_tuple]].append(key)
        else:
            unique_sets[articles_tuple] = key
            grouped_topics[key] = [key]

    final_topics = {}
    for group, topic_keys in grouped_topics.items():
        representative_topic = topic_keys[0]
        final_topics[" / ".join(topic_keys)] = topics[representative_topic]

    return final_topics

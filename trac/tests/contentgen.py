#!/usr/bin/python

import random


try:
    all_words = [x.strip() for x in open('/usr/share/dict/words').readlines() if x.strip().isalpha()]
except:
    all_words = [
        'one',
        'two',
        'three',
        'four',
        'five',
        'six',
        'seven',
        'eight',
        'nine',
        'ten',
    ]

def random_word():
    word = random.choice(all_words)
    # Do not return CamelCase words
    if word[0].isupper():
        word = word.lower().capitalize()
    return word

_random_unique_camels = []
def random_unique_camel():
    """Returns a unique camelcase word pair"""
    while True:
        camel = random_word().title() + random_word().title()
        if not camel in _random_unique_camels:
            break
    _random_unique_camels.append(camel)
    return camel

def random_sentence(word_count=None):
    if word_count == None:
        word_count = random.randint(1, 20)
    words = [random_word() for x in range(word_count)]
    return '%s.' % ' '.join(words)

def random_paragraph(sentence_count=None):
    if sentence_count == None:
        sentence_count = random.randint(1, 10)
    sentences = [random_sentence(random.randint(2, 15)) for x in range(sentence_count)]
    return '  '.join(sentences)

def random_page(paragraph_count=None):
    if paragraph_count == None:
        paragraph_count = random.randint(1, 10)
    paragraphs = [random_paragraph(random.randint(1, 5)) for x in range(paragraph_count)]
    return '\r\n\r\n'.join(paragraphs)

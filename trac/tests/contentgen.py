# -*- coding: utf-8 -*-
#
# Copyright (C) 2008-2023 Edgewall Software
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution. The terms
# are also available at https://trac.edgewall.org/wiki/TracLicense.
#
# This software consists of voluntary contributions made by many
# individuals. For the exact contribution history, see the revision
# history and logs, available at https://trac.edgewall.org/log/.

import random
import re
import uuid

try:
    isalpha = re.compile(r'[A-Za-z]+$').match
    with open('/usr/share/dict/words', 'r', encoding='utf-8') as f:
        all_words = list(filter(isalpha, map(lambda v: v.strip(), f)))
        del f
except IOError:
    with open('trac/tests/random_words.txt', 'r', encoding='utf-8') as f:
        all_words = f.read().split()


def random_word(min_length=1):
    word = random.choice(all_words)
    while len(word) < min_length:
        word = random.choice(all_words)
    # Do not return CamelCase words
    if word[0].isupper():
        word = word.lower().capitalize()
    return word


_random_unique_camels = []
def random_unique_camel():
    """Returns a unique camelcase word pair"""
    while True:
        camel = random_word(2).title() + random_word(2).title()
        if camel not in _random_unique_camels:
            break
    _random_unique_camels.append(camel)
    return camel


def random_sentence(word_count=None):
    """Generates a random sentence. The first word consists of the first 8
    characters of a uuid to ensure uniqueness.

    :param word_count: number of words in the sentence
    """
    if word_count is None:
        word_count = random.randint(1, 20)
    words = [random_word() for x in range(word_count - 1)]
    words.insert(0, str(uuid.uuid1()).split('-')[0])
    return '%s.' % ' '.join(words)


def random_paragraph(sentence_count=None):
    if sentence_count is None:
        sentence_count = random.randint(1, 10)
    return '  '.join(random_sentence(random.randint(2, 15))
                     for x in range(sentence_count))


def random_page(paragraph_count=None):
    if paragraph_count is None:
        paragraph_count = random.randint(1, 10)
    return '\r\n\r\n'.join(random_paragraph(random.randint(1, 5))
                           for x in range(paragraph_count))

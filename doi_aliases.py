import json, traceback, requests, types
from collections import defaultdict
from h_util import *

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode

only_doi_aliases = False

def add_doi_alias(alias, uri, updated):
    bundle = ''
    if alias.startswith('doi:'):
        if has_doi_alias == False:
            u = '\n%s (%s)\n' % (uri, updated)
            bundle += u
            has_doi_alias = True
        a = "\t%\n" % alias
        bundle += a
    return bundle

def add_alias(alias, uri, updated):
    bundle = ''
    bundle += '\n%s (%s)\n' % (uri, updated) 
    bundle += "\t%s\n" % alias
    return bundle

unique_uris = defaultdict(list)
for row in HypothesisUtils().search_all():
    unique_uris[row['uri']].append(row)
 
report = ''

for uri in unique_uris.keys():
    aliases = set()
    for row in unique_uris[uri]:
        has_doi_alias = False
        if uri != row['uri']:
            continue
        raw = HypothesisRawAnnotation(row)
        for link in row.links:
            if link.has_key('href') and link['href'] != uri:
                aliases.add(link['href'])
    bundle = ''
    updated = raw.updated
    if len(aliases):
        for alias in aliases:
            if only_doi_aliases:
                bundle = add_doi_alias(alias, uri, updated)
            else:
                bundle = add_alias(alias, uri, updated)
    report += bundle

f = open('./aliases.txt','w')
f.write(report.encode('utf-8'))
f.close()

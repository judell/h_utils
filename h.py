"""
/?method=activity

<<<<<<< Updated upstream
/?method=feed&tag=[TAG]
=======
/feed?tags=[TAG]
>>>>>>> Stashed changes

/?method=urlfeed&url=[URL]

<<<<<<< Updated upstream
/?method=user_widget&user=[USER]

/?method=multi_tag&tags=[TAG1,TAG2]
"""

import json, urllib, requests, re, traceback, types
from Hypothesis import Hypothesis, HypothesisUserActivity
=======
/multi_tag?tags=[TAG1,TAG2]
"""

import json, urllib, requests, re, traceback, types, pyramid
from h_util import *
>>>>>>> Stashed changes
from collections import defaultdict
from datetime import datetime
from feedgen.feed import FeedGenerator

from BaseHTTPServer import BaseHTTPRequestHandler
import urlparse, operator

#host = 'localhost'
host = 'h.jonudell.info'
port = 8080
host_port = 'http://' + host + ':' + str(port)
alt_stream = 'https://alt-stream.dokku.hypothes.is'


class GetHandler(BaseHTTPRequestHandler):

    def respond_200(self, mime_type, body):
        self.send_response(200)
        self.send_header(  'Content-Type' , mime_type )
        self.send_header(  'Content-Length' , str(len(body)) )
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):

        print self.path

        if self.path == '/js':             # handle exactly 1 file
            try:
                f = open('h.js')
                body = f.read()
                f.close()
                self.respond_200('text/javascript; charset=UTF-8', body)
                return;
            except:
                print traceback.format_exc()

        if not "method=" in self.path:     # and just these methods
            return   
         
        parsed_path = urlparse.urlparse(self.path)
        q = parsed_path.query
        method = urlparse.parse_qs(q)['method'][0]
        if method == 'feed':
            body = _feed(q, 'tag')
            self.respond_200('application/xml; charset=UTF-8', body)
            return;
        if method == 'urlfeed':
            body = _feed(q, 'url')
            self.respond_200('application/xml; charset=UTF-8', body)
            return;
        if method == 'activity':
            body = activity(q)
            self.respond_200('text/html; charset=UTF-8', body)
            return;
        if method == 'user_widget':
            body = user_activity(q)
            self.respond_200('text/html; charset=UTF-8', body)
            return;
        if method == 'multi_tag':
            body = multi_tag(q)
            self.respond_200('text/html; charset=UTF-8', body)
            return;

def multi_tag(q):
    tags = urlparse.parse_qs(q)['tags'][0]
    tags = tags.split(',')
    tags = [t.strip() for t in tags]
    tags = [urllib.quote(t) for t in tags]
    args = ['tags=' + a for a in tags]
    args = '&'.join(args)
<<<<<<< Updated upstream
    h_url = 'https://hypothes.is/api/search?limit=200&' + args
    s = requests.get(h_url).text.decode('utf-8')
    j = json.loads(s)
    return make_multi_tag(j,tags)
=======
    j = call_search_api(args)
    body = make_multi_tag(j,tags)
    return Response(body.encode('utf-8'))

def dispatch(request):
    q = urlparse.parse_qs(request.query_string)
    if q.has_key('method'):
        if q['method'][0] == 'urlfeed':
            return urlfeed(request)
        if q['method'][0] == 'feed':
            return feed(request)
        if q['method'][0] == 'activity':
            return activity(request)
        if q['method'][0] == 'multi_tag':
            return multi_tag(request)
>>>>>>> Stashed changes

def make_multi_tag(j,tags):
    rows = j['rows']
    html = """<html>
<head>
 <style>
 body { font-family:verdana;margin:.5in }
 h1 { font-weight: bold; margin-bottom:10pt }
 p.attribution { font-size: smaller; }
 </style>
<body>%s</body>
</html>
""" 
    s = '<h1>Search for tags: ' + ','.join(tags) + '</h1>'
    s += '<h2>found ' + str(len(rows)) + '</h2><hr>'
    for row in rows:
        raw = HypothesisRawAnnotation(row)
        updated = raw.updated
        user = raw.user
        uri = raw.uri
        text = raw.text
        tags = raw.tags
        s += '<p><a href="%s">%s</a></p>' % ( uri, uri)
        s += '<p>%s</p>' % text
        tags = ['<a href="' + host_port + '/?method=multi_tag&tags=' + urllib.quote(t) + '">' + t + '</a>' for t in tags]
        s += '<p class="attribution">%s - %s - %s</p>' % ( user, updated, ', '.join(tags))
        s += '<hr>'
    return (html % s).encode('utf-8')

def _feed(q,facet):
    value = urlparse.parse_qs(q)[facet][0]
    if facet == 'tag':
        h_url = 'https://hypothes.is/api/search?tags=' + value
    if facet == 'url':
        h_url = 'https://hypothes.is/api/search?uri=' + value
    s = requests.get(h_url).text.decode('utf-8')
    j = json.loads(s)
    return make_feed(j, facet, value)

<<<<<<< Updated upstream
def activity(q):
    h_url = 'https://hypothes.is/api/search?limit=1000'
    s = requests.get(h_url).text.decode('utf-8')
    j = json.loads(s)
    return make_activity(j)

def user_activity(q):
    user = urlparse.parse_qs(q)['user'][0]
    h_url = 'https://hypothes.is/api/search?limit=200&user=' + user
    s = requests.get(h_url).text.decode('utf-8')
    j = json.loads(s)
    return get_user_activity(j, user)
=======
def activity(request):
    j = HypothesisUtils().call_search_api()
    body = make_activity(j)

    return Response(body.encode('utf-8'))
>>>>>>> Stashed changes

def make_activity(j):
    users = defaultdict(int)
    days = defaultdict(int)
    rows = j['rows']
    for row in rows:
        raw = HypothesisRawAnnotation(row)
        created = row.updated[0:19]
        day = created[0:10]
        days[day] += 1
        user = row.user
        users[user] += 1
        uri = row.uri

    days = sorted(days.items(), key=operator.itemgetter(0,1), reverse=True)

    users = sorted(users.items(), key=operator.itemgetter(1,0), reverse=True)

    html = """
<html>
<head><style>
body { font-family: verdana; margin: .2in; }
</style></head>
<body>
<h1>Hypothesis recent 200 annotations</h1>
%s
</body>
</html>
 """
    s = '<p>days: %s </p>' % len(days)
    for day in days:
        s += '<div>%s: %s</div>' % (day[0], day[1])

    s += '<p>users: %s</p>' % len(users)
    for user in users:
        uname = re.sub('.+\\:','',user[0])
        uname = re.sub('@.+','',uname)
        url = alt_stream + '/stream.alt?user=' +  uname
        s += '<div><a target="_new" title="see annotation activity" href="%s">%s</a>: %s</div>' % (url, uname, user[1])

    return html % s

def make_feed(j, facet,  value):
    url = host_port + '/'
    if facet == 'tag':
        url += '?method=feed&tag=' + value
    if facet == 'url':
        url += '?method=feed&' + facet + '=' + value
    rows = j['rows']
    fg = FeedGenerator()
    fg.title('h stream for ' + facet + ' ' + value)
    fg.description('desc')
    fg.link(href='%s' % (url), rel='self')
    fg.id(url)
    for r in rows:
        raw = HypothesisRawAnnotation(r)
        user = raw.user
        uri = raw.uri
        doc_title = raw.doc_title
        title = 'note by %s on "%s" (%s)' % ( user, doc_title, uri )
        fe = fg.add_entry()
        fe.title(title)
        fe.link(href="https://hypothes.is/a/%s" % r['id'])
        fe.id("https://hypothes.is/a/%s" % r['id'])
        fe.author({'name': r['user']})
        content = ''
        if r.has_key('text'):
            content += ': ' + r['text']
        if r.has_key('tags'):
            content += ' [tags: %s]' % ','.join(r['tags'])
        fe.content(content)
    str = fg.atom_str(pretty=True)
    return str.encode('utf-8')

<<<<<<< Updated upstream
def get_user_activity(j, user):

    activity = HypothesisUserActivity(limit=15)
    
    for row in j['rows']:
        activity.add_row(row)
    activity.sort()

    s = '<h1>Hypothesis activity for %s</h1>' % user

    for uri in activity.uris_by_recent_update:
        bundles = activity.uri_bundles[uri]
        for bundle in bundles:
            dt_str = bundle['updated']
            dt = datetime.strptime(dt_str[0:16], "%Y-%m-%dT%H:%M")
            when = Hypothesis.friendly_time(dt)
            uri = bundle['uri']
            doc_title = bundle['doc_title']
            via_url = Hypothesis().via_url
            try:
                s += """<div class="stream-url">
    <a target="_new" class="ng-binding" href="%s">%s</a> 
    (<a title="use Hypothesis proxy" target="_new" href="{%s}/{%s}">via</a>)
    <span class="annotation-timestamp small pull-right ng-binding ng-scope">{%s}</span> 
    </div>""" % (uri, doc_title, via_url, uri, when)
            except:
                tb = traceback.format_exc()

            references_html = bundle['references_html']
            quote_html = bundle['quote_html']
            text_html = bundle['text_html']
            tag_html = bundle['tag_html']

            is_page_note = bundle['is_page_note']

            if quote_html != '':
                s += """<div class="stream-quote">%s</div>"""  % quote_html

            if text_html != '' and references_html == '':
                s += """<div class="stream-text">%s</div>""" %  text_html

            if references_html != '':
                s += '<p class="stream-reference">%s</p>\n' % references_html

            if tag_html != '':
                s += '<div class="stream-tags">%s</div>' % tag_html

    s = Hypothesis.get_stream_template() % (s)

    return s.encode('utf-8')

def add_or_append(dict, key, val):
    if dict.has_key(key):
        dict[key].append(val)
    else:
        dict[key] = [val]
    return dict
=======
if __name__ == '__main__':

    from wsgiref.simple_server import make_server
    from pyramid.config import Configurator
    from pyramid.response import Response

    config = Configurator()
    config.add_route('dispatch', '/')
    config.add_view(dispatch, route_name='dispatch')

    config.add_route('feed', '/feed')
    config.add_view(feed, route_name='feed')

    config.add_route('urlfeed', '/urlfeed')
    config.add_view(urlfeed, route_name='urlfeed')

    config.add_route('activity', '/activity')
    config.add_view(activity, route_name='activity')

    config.add_route('multi_tag', '/multi_tag')
    config.add_view(multi_tag, route_name='multi_tag')

    config.add_route('alt_stream', '/stream.alt')
    config.add_view(HypothesisStream.alt_stream, route_name='alt_stream')

    config.add_route('alt_stream_js', '/stream.alt.js')
    config.add_view(HypothesisUtils.alt_stream_js, route_name='alt_stream_js')

    app = config.make_wsgi_app()
    server = make_server(host, port, app)
    server.serve_forever()
>>>>>>> Stashed changes
    



 


  
 

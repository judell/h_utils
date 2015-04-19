import json, urllib2
from feedgen.feed import FeedGenerator

from BaseHTTPServer import BaseHTTPRequestHandler
import urlparse, operator

class GetHandler(BaseHTTPRequestHandler):
    
    def do_GET(self):
        if not "method=" in self.path:
            return    
        parsed_path = urlparse.urlparse(self.path)
        q = parsed_path.query
        method = urlparse.parse_qs(q)['method'][0]
        if method == 'feed':
            self.wfile.write(json2atom(q))
            return;
        if method == 'activity':
            self.wfile.write(activity(q))
            return;
        if method == 'user_urls':
            self.wfile.write(user_urls(q))
            return;


def json2atom(q):
    tag = urlparse.parse_qs(q)['tag'][0]
    h_url = 'https://hypothes.is/api/search?tags=' + tag
    s = urllib2.urlopen(h_url).read()
    j = json.loads(s)
    return make_feed(j, tag)

def activity(q):
    h_url = 'https://hypothes.is/api/search?limit=1000'
    s = urllib2.urlopen(h_url).read()
    j = json.loads(s)
    return make_activity(j)

def user_urls(q):
    user = urlparse.parse_qs(q)['user'][0]
    h_url = 'https://hypothes.is/api/search?limit=1000&user=' + user
    s = urllib2.urlopen(h_url).read()
    j = json.loads(s)
    return make_user_urls(j, user)
    

def make_activity(j):
    users = {}
    days = {}
    details = ''
    rows = j['rows']
    for row in rows:
        created = row['created'][0:19]
        day = created[0:10]
        days = add_or_increment(days,day)
        user = row['user']
        users = add_or_increment(users,user)
        uri = row['uri']
        details += '<div>created %s user %s uri %s</div>' % ( created, user, uri)

    days = sorted(days.items(), key=operator.itemgetter(0,1), reverse=True)

    users = sorted(users.items(), key=operator.itemgetter(1,0), reverse=True)

    s = '<p>most recent 200 annotations</p>'

    s += '<p>days: %s </p>' % len(days)
    for day in days:
        s += '<div>%s: %s</div>' % (day[0], day[1])

    s += '<p>users: %s</p>' % len(users)
    for user in users:
        s += '<div>%s: %s</div>' % (user[0], user[1])

    s += '<p>details</p>'
    s += details
    return s


def make_feed(j, tag):
    host = 'http://wiki.elmcity.info:8080/'
    url = host + '?method=feed&tag=' + tag
    rows = j['rows']
    fg = FeedGenerator()
    fg.title('h stream for tag ' + tag)
    fg.description('desc')
    fg.link(href='%s' % (url), rel='self')
    fg.id(url)
    for r in rows:
        fe = fg.add_entry()
        fe.id(r['uri'])
        fe.title(r['uri'])
        fe.link(href="%s" % r['uri'])
        fe.author({'name':'h'})
        fe.content(r['uri'])
    return fg.atom_str(pretty=True)

def make_user_urls(j, user):
    urls = {}
    texts = {}
    titles = {}
    datetimes = {}
    tags = {}
    s = '<h1>urls annotated by %s</h1>' % user
    for row in j['rows']:
        url = row['uri'].replace('https://via.hypothes.is/h/','')
        if url.startswith('urn:'):
            continue
        add_or_increment(urls, url)
        datetimes[url] = row['updated']
        try:
            title = row['document']['title']
            if ( isinstance(title, list)):
                titles[url] = title[0]
            else:
                titles[url] = title
        except:
            titles[url] = url # it's a reply?
        try:
            text = row['text']
            if len(text):
                add_or_append(texts, url, text)
        except:
            pass
        try:
            if len(row['tags']):
                for t in row['tags']:
                    add_or_append(tags, url, t)
        except:
            pass

    date_ordered_urls = datetimes.keys()
    date_ordered_urls.reverse()

    for url in date_ordered_urls:
        taglist = '</i>, <i>'.join(tags[url])  if tags.has_key(url) else ''
        s += '<p><a href="https://via.hypothes.is/h/%s">%s</a> <i>%s</i></p>' % ( url, titles[url], taglist)
        if texts.has_key(url):
            list_of_texts = texts[url]
            list_of_texts.reverse()
            for text in list_of_texts: 
                s += '<blockquote>%s</blockquote>' % text
    s = """<html>
<head>
<style>
body { font-family: verdana; margin: .5in }
</style>
<body>
%s
</body>
</html>
""" % (s)
    return s.encode('utf-8')

def add_or_increment(dict, key):
    if dict.has_key(key):
        dict[key] += 1
    else:
        dict[key] = 1
    return dict

def add_or_append(dict, key, val):
    if dict.has_key(key):
        dict[key].append(val)
    else:
        dict[key] = [val]
    return dict
    

if __name__ == '__main__':
    from BaseHTTPServer import HTTPServer
#    server = HTTPServer(('h.jonudell.info', 8080), GetHandler)
    server = HTTPServer(('', 8080), GetHandler)
    print 'Starting server, use <Ctrl-C> to stop'
    server.serve_forever()

####
for row in j['rows']:
  uri = row['uri'].replace('https://via.hypothes.is/h/','')
  add_or_increment(urls, uri)

 


  
 

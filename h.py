import json, urllib2, re
from feedgen.feed import FeedGenerator

from BaseHTTPServer import BaseHTTPRequestHandler
import urlparse, operator

host = 'h.jonudell.info'
#host = 'localhost'
port = 8080
host_port = 'http://' + host + ':' + str(port)

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
        uname = re.sub('.+\\:','',user[0])
        uname = re.sub('@.+','',uname)
        url = host_port + '/?method=user_urls&user=' + uname
        s += '<div><a target="user activity" title="see annotation activity" href="%s">%s</a>: %s</div>' % (url, uname, user[1])

    s += '<p>details</p>'
    s += details
    return s


def make_feed(j, tag):
    url = host_port + '?method=feed&tag=' + tag
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
    s = '<h1>urls annotated by %s</h1>' % user
    for row in j['rows']:
        url = row['uri'].replace('https://via.hypothes.is/h/','')
        if url.startswith('urn:'):
            continue
        add_or_increment(urls, url)
        datetimes[url] = row['created']
        try:
            title = row['document']['title'].decode('utf-8')
            if ( isinstance(title, list)):
                titles[url] = title[0]
            else:
                titles[url] = title
        except:
            titles[url] = url # it's a reply?
        try:
            if len(row['tags']):
                tags = ', '.join(row['tags'])
                tags = '<i>(tags: %s)</i>' % tags
            else:
                tags = ''
            selector = row['target'][0]['selector']
            for sel in selector:
                if sel.has_key('exact'):
                    target = sel['exact'].decode('utf-8')
                    text = row['text'].decode('utf-8')
                    add_or_append(texts, url, (target,text,tags))
        except:
            pass

    date_ordered_urls = sorted(datetimes.items(), key=operator.itemgetter(1,0), reverse=True)

    for tuple in date_ordered_urls:
        url = tuple[0]
        dt = tuple[1]
        when = dt[0:16].replace('T',' ')
        s += '<p><b><span style="font-size:smaller">%s</span></b> <a href="https://via.hypothes.is/h/%s">%s</a></p>' % (when, url, titles[url])
        if texts.has_key(url):
            list_of_texts = texts[url]
            list_of_texts.reverse()
            for target_and_text_and_tags in list_of_texts: 
                target = target_and_text_and_tags[0]
                text = target_and_text_and_tags[1]
                tags = target_and_text_and_tags[2]
                s += '<blockquote><i>%s</i></blockquote><blockquote style="margin-left:10%%">%s %s</blockquote>' % (target,text, tags)
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
    server = HTTPServer((host, port), GetHandler)
    print 'Starting server, use <Ctrl-C> to stop'
    server.serve_forever()

####
for row in j['rows']:
  uri = row['uri'].replace('https://via.hypothes.is/h/','')
  add_or_increment(urls, uri)

 


  
 

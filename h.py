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
        if method == 'json2rss':
            self.wfile.write(json2atom(q))
            return;
        if method == 'activity':
            self.wfile.write(activity(q))
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
    url = host + '?tag=' + tag
    rows = j['rows']
    fg = FeedGenerator()
    fg.title('h stream for tag ' + tag)
    fg.description('desc')
    fg.link(href='%s' % (url) , rel='self')
    fg.id(url)
    for r in rows:
        fe = fg.add_entry()
        fe.id(r['uri'])
        fe.title(r['uri'])
        fe.link(href="%s" % r['uri'])
        fe.author({'name':'h'})
        fe.content('tagged item')
    return fg.atom_str(pretty=True)

def add_or_increment(dict, key):
    if dict.has_key(key):
        dict[key] += 1
    else:
        dict[key] = 1
    return dict

if __name__ == '__main__':
    from BaseHTTPServer import HTTPServer
    server = HTTPServer(('', 8080), GetHandler)
    print 'Starting server, use <Ctrl-C> to stop'
    server.serve_forever()


 

  
 

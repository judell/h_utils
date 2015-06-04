"""
/?method=activity

/?method=feed&tag=[TAG]

/?method=urlfeed&url=[URL]

/?method=user_widget&user=[USER]
"""

import json, urllib2, re, chardet, traceback
from datetime import datetime
from feedgen.feed import FeedGenerator

from BaseHTTPServer import BaseHTTPRequestHandler
import urlparse, operator

#host = 'localhost'
host = 'h.jonudell.info'
port = 8080
host_port = 'http://' + host + ':' + str(port)

class GetHandler(BaseHTTPRequestHandler):
    
    def do_headers(self, mime_type, body):
        self.send_response(200)
        self.send_header(  'Content-Type' , mime_type )
        self.send_header(  'Content-Length' , str(len(body)) )
        self.end_headers()

    def do_GET(self):
        if not "method=" in self.path:
            return    
        parsed_path = urlparse.urlparse(self.path)
        q = parsed_path.query
        method = urlparse.parse_qs(q)['method'][0]
        if method == 'feed':  # default is by tag
            body = _feed(q, 'tag')
            self.do_headers('application/xml; charset=UTF-8', body)
            self.wfile.write(body)
            return;
        if method == 'urlfeed':
            body = _feed(q, 'url')
            self.do_headers('application/xml; charset=UTF-8', body)
            self.wfile.write(body)
            return;
        if method == 'activity':
            body = activity(q)
            self.do_headers('text/html; charset=UTF-8', body)
            self.wfile.write(body)
            return;
        if method == 'user_widget':
            body = user_widget(q)
            self.do_headers('text/html; charset=UTF-8', body)
            self.wfile.write(body)
            return;
        if method == 'multi_tag':
            body = multi_tag(q)
            self.do_headers('text/html; charset=UTF-8', body)
            self.wfile.write(body)
            return;

def multi_tag(q):
    tags = urlparse.parse_qs(q)['tags'][0]
    tags = tags.split(',')
    tags = [t.strip() for t in tags]
    args = ['tags=' + a for a in tags]
    args = '&'.join(args)
    h_url = 'https://hypothes.is/api/search?' + args
    s = urllib2.urlopen(h_url).read()
    j = json.loads(s)
    return make_multi_tag(j,tags)

def make_multi_tag(j,tags):
    rows = j['rows']
    tmpl = """<html>
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
        updated = row['updated'][0:19]
        user = row['user'].replace('acct:','').replace('@hypothes.is','')
        uri = row['uri']
        text = row['text']
        tags = row['tags']
        s += '<p><a href="%s">%s</a></p>' % ( uri, uri)
        s += '<p>%s</p>' % text
        s += '<p class="attribution">%s - %s - %s</p>' % ( user, updated, ','.join(tags))
        s += '<hr>'
    return tmpl % s


def _feed(q,facet):
    value = urlparse.parse_qs(q)[facet][0]
    if facet == 'tag':
        h_url = 'https://hypothes.is/api/search?tags=' + value
    if facet == 'url':
        h_url = 'https://hypothes.is/api/search?uri=' + value
    s = urllib2.urlopen(h_url).read()
    s = s.decode('utf-8')
    j = json.loads(s)
    return make_feed(j, facet, value)

def activity(q):
    h_url = 'https://hypothes.is/api/search?limit=1000'
    s = urllib2.urlopen(h_url).read()
    j = json.loads(s)
    return make_activity(j)

def user_widget(q):
    user = urlparse.parse_qs(q)['user'][0]
    h_url = 'https://hypothes.is/api/search?limit=200&user=' + user
    s = urllib2.urlopen(h_url).read()
    s = s.decode('utf-8')
    j = json.loads(s)
    return make_user_widget(j, user, 15)

def friendly_time(dt):
    now = datetime.now()
    delta = now - dt

    minute = 60
    hour = minute * 60
    day = hour * 24
    month = day * 30
    year = day * 365

    diff = delta.seconds + (delta.days * day)

    if diff < 10:
        return "just now"
    if diff < minute:
        return str(diff) + " seconds ago"
    if diff < 2 * minute:
        return "a minute ago"
    if diff < hour:
        return str(diff / minute) + " minutes ago"
    if diff < 2 * hour:
        return "an hour ago"
    if diff < day:
        return str(diff / hour) + " hours ago"
    if diff < 2 * day:
        return "a day ago"
    if diff < month:
        return str(diff / day) + " days ago"
    if diff < 2 * month:
        return "a month ago"
    if diff < year:
        return str(diff / month) + " months ago"
    return str(diff / year) + " years ago"

def make_activity(j):
    users = {}
    days = {}
    details = ''
    rows = j['rows']
    for row in rows:
        created = row['updated'][0:19]
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
        url = host_port + '/?method=user_widget&user=' + uname
        s += '<div><a target="_new" title="see annotation activity" href="%s">%s</a>: %s</div>' % (url, uname, user[1])

    s += '<p>details</p>'
    s += details
    return s

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
        fe = fg.add_entry()
        fe.title(r['uri'])
        fe.link(href="https://hypothes.is/a/%s" % r['id'])
        fe.id("https://hypothes.is/a/%s" % r['id'])
        fe.author({'name': r['user']})
        if r.has_key('text'):
            fe.content(r['user'] + ": " + r['text'])
        else:
            fe.content(r['user'] + ": " + r['uri'])
    str = fg.atom_str(pretty=True)
    return str.encode('utf-8')

def get_user_activity(j, user):
    texts = {}
    titles = {}
    datetimes = {}
    
    for row in j['rows']:
        url = row['uri'].replace('https://via.hypothes.is/h/','').replace('https://via.hypothes.is/','')
        #if url.startswith('urn:'):
        #    continue
        #add_or_increment(urls, url)
        datetimes[url] = row['updated']
        try:
            title = row['document']['title']
            if ( isinstance(title, list)):
                titles[url] = title[0]
            else:
                titles[url] = title
        except:
            titles[url] = url # it's a reply?
        tag_html = ''
        try:
            if len(row['tags']):
                tag_items = []
                for tag in row['tags']:
                    tag_items.append('<li><span class="tag-item">%s</span></li>' % tag)
                tag_html = '<ul>%s</ul>' % '\n'.join(tag_items)
            if row.has_key('target') is False:
                continue
            if len(row['target']) == 0:
                continue
            selector = row['target'][0]['selector']
            for sel in selector:
                if sel.has_key('exact'):
                    target = sel['exact']
                    text = row['text']
                    text = re.sub('\n+','<p>', text)
                    img_pat = '!\[Image Description\]\(([^\)]+)\)'
                    text = re.sub(img_pat, r'<img src="\1">', text)
                    url_pat = '\[([^\]]+)\]\(([^\)]+)\)'
                    text = re.sub(url_pat, r'<a href="\2">\1</a>', text)
                    add_or_append(texts, url, (target,text,tag_html))
        except:
            print traceback.format_exc()
    return datetimes, texts, titles

def make_user_widget(j, user, limit):
    
    datetimes, texts, titles = get_user_activity(j, user)

    date_ordered_urls = sorted(datetimes.items(), key=operator.itemgetter(1,0), reverse=True)
    
    s = '<h1>Hypothesis activity for %s</h1>' % user

    for tuple in date_ordered_urls[0:limit]:
        url = tuple[0]
        dt_str = tuple[1]
        dt = datetime.strptime(dt_str[0:16], "%Y-%m-%dT%H:%M")
        #when = dt.strftime('%d %b %Y %H:%M')
        when = friendly_time(dt)
        s += '<div class="stream-url"><a target="_new" class="ng-binding" href="https://via.hypothes.is/%s">%s</a> <span class="annotation-timestamp small pull-right ng-binding ng-scope">%s</span> </div>' % (url, titles[url], when)
        if texts.has_key(url):
            list_of_texts = texts[url]
            list_of_texts.reverse()
            for target_and_text_and_tags in list_of_texts: 
                target = target_and_text_and_tags[0]
                text = target_and_text_and_tags[1]
                tags = target_and_text_and_tags[2]
                s += '<div class="stream-quote"><span class="annotation-quote">%s</span></div><div class="stream-comment">%s</div>' % (target,text)
                if tags != '':
                    s += '<div class="stream-tags">%s</div>' % tags
    s = """<html>
<head>
 <link rel="stylesheet" href="https://hypothes.is/assets/styles/app.min.css" />
 <link rel="stylesheet" href="https://hypothes.is/assets/styles/hypothesis.min.css" />
 <style>
 body { padding: 10px; font-size: 10pt }
 h1 { font-weight: bold; margin-bottom:10pt }
 .stream-quote { margin-bottom: 4pt; }
 .stream-url { margin-bottom: 4pt; overflow:hidden}
 .stream-comment { margin-bottom: 4pt; margin-left:10%%; word-wrap: break-word }
 .stream-tags { margin-left: 10%%; margin-bottom: 4pt }
 .annotation-quote { padding: 0 }
 ul, li { display: inline }
 li { color: #969696; font-size: smaller; border: 1px solid #d3d3d3; border-radius: 2px; padding: 0 .4545em .1818em }
 img { max-width: 100%% }
 annotation-timestamp { margin-right: 20px }
 img { padding:10px }
 a { word-wrap: break-word }
 </style>
<body class="ng-scope">
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

 


  
 

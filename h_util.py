import requests
import json, types, re, operator, traceback, time, redis
from pyramid.response import Response
from datetime import datetime
from collections import defaultdict
from markdown import markdown
from bs4 import BeautifulSoup
import urlparse
from dateutil import parser
from datetime import date, timedelta
import matplotlib
matplotlib.use('svg')
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import cStringIO, re

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode


class HypothesisUtils:
    def __init__(self, username=None, password=None, limit=None, max_results=None):
        self.app_url = 'https://hypothes.is/app'
        self.api_url = 'https://hypothes.is/api'
        self.query_url = 'https://hypothes.is/api/search?{query}'
        self.anno_url = 'https://hypothes.is/a'
        self.via_url = 'https://via.hypothes.is'
        self.username = username
        self.password = password
        self.single_page_limit = 200 if limit is None else limit  # per-page, the api honors limit= up to (currently) 200
        self.multi_page_limit = 200 if max_results is None else max_results  # limit for paginated results

    def login(self):
        """Request an assertion, exchange it for an auth token."""
        # https://github.com/rdhyee/hypothesisapi 
        r = requests.get(self.app_url)
        cookies = r.cookies
        payload = {"username":self.username,"password":self.password}
        self.csrf_token = cookies['XSRF-TOKEN']
        data = json.dumps(payload)
        headers = {'content-type':'application/json;charset=UTF-8', 'x-csrf-token': self.csrf_token}
        r = requests.post(url=self.app_url  + "?__formid__=login", data=data, cookies=cookies, headers=headers)
        url = self.api_url + "/token?" + urlencode({'assertion':self.csrf_token})
        r = (requests.get(url=url,
                         cookies=cookies, headers=headers))
        self.token =  r.content

    def search_refs(self, id):
        """Get references for id."""
        refs = self.search( {'references':id } )
        return refs['rows']

    def search(self, params={}):
        """Call search API with no pagination, return JSON."""
        params['limit'] = self.single_page_limit
        h_url = self.query_url.format(query=urlencode(params))
        json = requests.get(h_url).json()
        return json
 
    def search_all(self, params={}):
        """Call search API with pagination, return rows."""
        params['limit'] = self.single_page_limit
        params['offset'] = 0
        while True:
            h_url = self.query_url.format(query=urlencode(params, True))
            r = requests.get(h_url).json()
            rows = r.get('rows')
            params['offset'] += len(rows)
            if params['offset'] > self.multi_page_limit:
                break
            if len(rows) is 0:
                break
            for row in rows:
                yield row

    def make_annotation_payload_with_target(self, url, start_pos, end_pos, prefix, quote, suffix, text, tags, link):
        """Create JSON payload for API call."""
        payload = {
            "uri": url,
            "user": 'acct:' + self.username + '@hypothes.is',
            "permissions": {
                "read": ["group:__world__"],
                "update": ['acct:' + self.username + '@hypothes.is'],
                "delete": ['acct:' + self.username + '@hypothes.is'],
                "admin":  ['acct:' + self.username + '@hypothes.is']
                },
            "document": {
                "link":  link   # link is a list of dict
                },
            "target": 
            [
                {
                "selector": 
                    [
                        {
                        "start": start_pos,
                        "end": end_pos,
                        "type": "TextPositionSelector"
                        }, 
                        {
                        "type": "TextQuoteSelector", 
                        "prefix": prefix,
                        "exact": quote,
                        "suffix": suffix
                        },
                    ]
                }
            ], 
            "tags": tags,
            "text": text
        }
        return payload

    def make_annotation_payload_without_target(self, url, text, tags, link):
        """Create JSON payload for API call."""
        payload = {
            "uri": url,
            "user": 'acct:' + self.username + '@hypothes.is',
            "permissions": {
                "read": ["group:__world__"],
                "update": ['acct:' + self.username + '@hypothes.is'],
                "delete": ['acct:' + self.username + '@hypothes.is'],
                "admin":  ['acct:' + self.username + '@hypothes.is']
                },
            "document": {
                "link":  link   # link is a list of dict
                },
            "tags": tags,
            "text": text
        }
        return payload

    def create_annotation_with_target(self, url=None, start_pos=None, end_pos=None, prefix=None, 
               quote=None, suffix=None, text=None, tags=None, link=None):
        """Call API with token and payload, create annotation"""
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json;charset=utf-8' }
        payload = self.make_annotation_payload_with_target(url, start_pos, end_pos, prefix, quote, suffix, text, tags, link)
        data = json.dumps(payload, ensure_ascii=False)
        r = requests.post(self.api_url + '/annotations', headers=headers, data=data)
        return r

    def create_annotation_without_target(self, url=None, text=None, tags=None, link=None):
        """Call API with token and payload, create page note (annotation with no target)"""
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json;charset=utf-8' }
        payload = self.make_annotation_payload_without_target(url, text, tags, link)
        data = json.dumps(payload, ensure_ascii=False)
        r = requests.post(self.api_url + '/annotations', headers=headers, data=data)
        return r

    def get_active_users(self):
        """Find users in results of a default API search."""
        j = self.search()
        users = defaultdict(int)
        rows = j['rows']
        for row in rows:
            raw = HypothesisRawAnnotation(row)
            user = raw.user
            users[user] += 1
        users = sorted(users.items(), key=operator.itemgetter(1,0), reverse=True)
        return users

    @staticmethod
    def friendly_time(dt):
        """Represent a timestamp in a simple, friendly way."""
        now = datetime.utcnow()
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

class HypothesisStream:

    def __init__(self, limit=None):
        self.uri_html_annotations = defaultdict(list)
        self.uri_updates = {}
        self.uris_by_recent_update = []
        self.limit = 200 if limit is None else limit
        self.by_url = 'no'
        self.selected_tags = None
        self.selected_user = None
        self.redis_host = 'h.jonudell.info'
        self.anno_dict = redis.StrictRedis(host=self.redis_host,port=6379, db=0) 
        self.ref_parents = redis.StrictRedis(host=self.redis_host,port=6379, db=1) 
        self.ref_children = redis.StrictRedis(host=self.redis_host,port=6379, db=2) 
        self.user_anno_counts = redis.StrictRedis(host=self.redis_host,port=6379, db=3) 
        self.user_replies = redis.StrictRedis(host=self.redis_host,port=6379, db=4) 
        self.user_icons = redis.StrictRedis(host=self.redis_host,port=6379, db=5)
        self.uri_users = redis.StrictRedis(host=self.redis_host,port=6379, db=6)
        self.user_annos = redis.StrictRedis(host=self.redis_host,port=6379, db=7)
        #self.user_anno_counts = redis.StrictRedis(host=self.redis_host,port=6379, db=8) 
        #self.user_replies = redis.StrictRedis(host=self.redis_host,port=6379, db=9) 
        self.current_thread = ''
        self.displayed_in_thread = defaultdict(bool)
        self.debug = False
        self.log = ''


    def add_row(self, row):
        """Add one API result to this instance."""
        raw = HypothesisRawAnnotation(row)

        uri = raw.uri
        updated = raw.updated
        if self.uri_updates.has_key(uri) == True:  # track most-recent update per uri
            if updated > self.uri_updates[uri]:
                self.uri_updates[uri] = updated
        else:
            self.uri_updates[uri] = updated

        html_annotation = HypothesisHtmlAnnotation(self, raw)
        self.uri_html_annotations[uri].append( html_annotation )

    def sort(self):
        """Order URIs by most recent update."""
        sorted_uri_updates = sorted(self.uri_updates.items(), key=operator.itemgetter(1), reverse=True)
        for update in sorted_uri_updates:
            self.uris_by_recent_update.append( update[0] )

    def init_tag_url(self):
        """Construct the base URL for a tag filter."""
        url = '/stream.alt?user='
        if self.selected_user is not None:
            url += self.selected_user
        url += '&by_url=' + self.by_url
        url += '&limit='
        if self.limit is not None:
            url += str(self.limit)
        return url

    def make_quote_html(self,raw):
        """Render an annotation's quote."""
        quote = ''
        target = raw.target
        try:
          if target is None:
              return quote 
          if isinstance(target,types.ListType) and len(target) == 0:
              return quote
          dict = {}
          if isinstance(target,types.ListType) and len(target) > 0:  # empirically observed it can be a list or not
              dict = target[0]
          else:
              dict = target
          if dict.has_key('selector') == False:
              return quote 
          selector = dict['selector']
          for sel in selector:
              if sel.has_key('exact'):
                  quote = sel['exact']
        except:
          s = traceback.format_exc()
          print s
        return quote

    def make_text_html(self, raw):
        """Render an annotation's text."""
        text = raw.text
        if raw.is_page_note:
            text = '<span title="Page Note" class="h-icon-insert-comment"></span> ' + text
        text = markdown(text)
        return text


    def make_tag_html(self, raw):
        """Render an annotation's tags."""
        row_tags = raw.tags
        if len(row_tags) == 0:
            return ''
        if self.selected_tags is None:
            self.selected_tags = ()

        tag_items = []
        for row_tag in row_tags:
            tags = list(self.selected_tags)
            url = self.init_tag_url()
            if row_tag in self.selected_tags:
                klass = "selected-tag-item"
                tags.remove(row_tag)
                url += '&tags=' + ','.join(tags)
                tag_html = '<a class="%s" title="remove filter on this tag" href="%s">%s</a>' % (klass, url, row_tag )
            else:
                klass = "tag-item"
                tags.append(row_tag)
                url += '&tags=' + ','.join(tags)
                tag_html = '<a class="%s" title="add filter on this tag" href="%s">%s</a>' % (klass, url, row_tag)
            tag_items.append('<li>%s</li>' % (tag_html))
        return '<ul>%s</ul>' % '\n'.join(tag_items)

    def get_active_user_data(self, q):
        """Marshall data about active users."""
        if q.has_key('user'):
            user = q['user'][0]
            user, picklist, userlist = self.make_active_users_selectable(user=user)
        else:
            user, picklist, userlist = self.make_active_users_selectable(user=None)
        userlist = [x[0] for x in userlist]
        return user, picklist, userlist

    @staticmethod
    def alt_stream(request):
        """Entry point called from views.py (in H dev env) or h.py in this project."""
        q = urlparse.parse_qs(request.query_string)
        h_stream = HypothesisStream()
        h_stream.anno_dict = redis.StrictRedis(host=h_stream.redis_host,port=6379, db=0) 
        if q.has_key('tags'):
            tags = q['tags'][0].split(',')
            tags = [t.strip() for t in tags]
            tags = tuple(tags)
        else:
            tags = None
        if q.has_key('by_url'):
            h_stream.by_url=q['by_url'][0]
        else:
            h_stream.by_url = 'yes'
        user, picklist, userlist = h_stream.get_active_user_data(q)  
        if q.has_key('user'):
            user = q['user'][0]
            #if user not in userlist:
            #    picklist = ''
        if h_stream.by_url=='yes':
            head = '<h1 class="stream-picklist">recently active user %s</h1>' % (picklist)
            head += '<h1>urls recently annotated</h1>'
            body = h_stream.make_alt_stream(user=None, tags=tags)
        else:
            head = '<h1 class="stream-picklist">recently active users %s</h1>' % (picklist)
            head += '<h1 class="url-view-toggle"><a href="/stream.alt?by_url=yes">view recent annotations by url</a></h1>'
            try:
                timeline_counts, timeline_days = h_stream.make_timeline_data(user)
                first_day = timeline_days[0]
                timeline = h_stream.create_timeline(timeline_counts, timeline_days)
                anno_counts = h_stream.user_anno_counts.get(user)
                user_replies = h_stream.user_replies.get(user) 
                head += '<h1 class="user-contributions">Since %s %s has contributed %s annotations, of which %s were replies</h1>' % (first_day, user, anno_counts, user_replies)
                if len(timeline_days) > 15:
                    head += timeline
            except:
                print traceback.format_exc()
            head += '<h1 class="stream-active-users-widget">These urls were recently annotated by %s</h1>' % user
            body = h_stream.make_alt_stream(user=user, tags=tags)
        html = HypothesisStream.alt_stream_template( {'head':head,  'main':body} )
        h_stream.anno_dict.connection_pool.disconnect()
        return Response(html.encode('utf-8'))

    def show_friendly_time(self, updated):
        dt_str = updated
        dt = datetime.strptime(dt_str[0:16], "%Y-%m-%dT%H:%M")
        when = HypothesisUtils.friendly_time(dt)
        return when

    def display_url(self, html_annotation, uri):
        uri = uri.replace('https://via.hypothes.is/static/__shared/viewer/web/viewer.html?file=/id_/','')
        id = html_annotation.raw.id
        if self.displayed_in_thread[id]:
            return ''
        """Render an annotation's URI."""
        when = self.show_friendly_time(html_annotation.raw.updated)
        doc_title = html_annotation.raw.doc_title
        via_url = HypothesisUtils().via_url
        s = '<div class="stream-url">'
        photo_url = self.user_icons.get(html_annotation.raw.user)
        photo_url = 'http://jonudell.net/h/generic-user.jpg' if photo_url == None else photo_url
        s += '<img class="user-image-small" src="%s"/>' % photo_url
        if uri.startswith('http'):
            s += """<a target="_new" class="ng-binding" href="%s">%s</a> 
(<a title="use Hypothesis proxy" target="_new" href="%s/%s">via</a>)"""  % (uri, doc_title, via_url, uri)
        else:
            s += doc_title
        s += """<span class="small pull-right">%s</span>
</div>""" % when
        try:
            users = self.uri_users.get(uri)
            if users is not None and len(users) > 1:
                users = set(json.loads(users))
                users.remove(html_annotation.raw.user)
                if len(users):
                    users = ['<a href="/stream.alt?by_url=no&user=%s">%s</a>' % (user, user) for user in users]
                    s += '<p class="other-users">also annotated by %s</p>' % ', '.join(users)
        except:
            print traceback.format_exc()
        return s

    def make_html_annotation(self, html_annotation=None, level=None):
            """Assemble rendered parts of an annotation into one HTML element."""
            s = ''
        
            id = html_annotation.raw.id

            if level > 0:
                s += '<div id="%s" class="reply reply-%s">' % ( id, level )
            else:
                s += '<div id=%s" class="stream-annotation">' % id
        
            #if self.by_url == 'yes':
            #    user = html_annotation.raw.user
            #    s += '<p class="stream-user"><a href="/stream.alt?user=%s&by_url=no">%s</a></p>' % (user, user)
            
            quote_html = html_annotation.quote_html
            text_html = html_annotation.text_html
            tag_html = html_annotation.tag_html
        
            is_page_note = html_annotation.raw.is_page_note
        
            if quote_html != '':
                s += """<p class="annotation-quote">%s</p>"""  % quote_html
        
            if text_html != '':
                s += """<p class="stream-text">%s</p>""" %  text_html 
        
            if tag_html != '':
                s += '<p class="stream-tags">%s</p>' % tag_html

            user = html_annotation.raw.user
            user_sig = '<a href="/stream.alt?by_url=no&user=%s">%s</a>' % ( user, user )
            time_sig = self.show_friendly_time(html_annotation.raw.updated) 
            s += '<p class="user-sig">%s %s</a>' % ( user_sig, time_sig ) 

            s += '</div>'

            return s

    def make_singleton_or_thread_html(self, id):
        self.current_thread = ''
        self.show_thread(id, level=0)
        return self.current_thread

    def make_alt_stream(self, user=None, tags=None):
        """Do requested API search, organize results."""

        #self.debug = True

        params = { 'limit': self.limit }

        if user is not None:
            self.selected_user = user
            params['user'] = user

        if tags is not None:
            self.selected_tags = tags
            params['tags'] = tags

        for row in HypothesisUtils().search_all(params):
           self.add_row(row)
        self.sort()

        s = ''
        for uri in self.uris_by_recent_update:
            html_annotations = self.uri_html_annotations[uri]

            s += self.display_url(html_annotations[0], uri)  

            for i in range(len(html_annotations[1:])):

                html_annotation = html_annotations[i]
                if html_annotation == '':
                    continue
             
                id = html_annotation.raw.id

                if self.debug: 
                    self.log += '%s, %s\n' % ( uri, id )

                if self.ref_parents.get(id) is not None:   # if part of thread, display whole thread
                    id = self.find_thread_root(id)
               
                if self.displayed_in_thread[id] == False:
                    s += '<div class="paper">'
                    s += self.make_singleton_or_thread_html(id)
                    s += '</div>'

        return s

    def find_thread_root(self, id):
        root = self.ref_parents.get(id)
        if root is None:
            return id
        while root is not None:
            id = self.ref_parents.get(root)
            if id is None:
                return root
            else:
                root = id
        assert(id is not None)
        return root

    def show_thread(self, id, level=None):
        if self.displayed_in_thread[id]:
            return
        if self.anno_dict.exists(id) == False:
            return
        try:
            if self.anno_dict.get(id) == None:
                print '%s not found in anno_dict: ' % id
                return
            row = json.loads(self.anno_dict.get(id))
            raw = HypothesisRawAnnotation(row)
            html_annotation = HypothesisHtmlAnnotation(self, raw)
            self.current_thread += self.make_html_annotation(html_annotation, level)
            self.displayed_in_thread[id] = True
            children_json = self.ref_children.get(id)
            if children_json is not None:
                for child in json.loads(children_json):
                    self.show_thread(child, level + 1 )
        except:
            traceback.print_exc()

    def make_active_users_selectable(self, user=None):
        """Enumerate active users, enable selection of one."""
        active_users = HypothesisUtils().get_active_users()
        most_active_user = active_users[0][0]
        select = ''
        for active_user in active_users:
            if user is not None and active_user[0] == user:
                option = '<option selected value="%s">%s (%s)</option>'
            else:
                option = '<option value="%s">%s (%s)</option>'
            option = option % (active_user[0], active_user[0], active_user[1])
            select += option
        select = """<select class="stream-active-users" name="active_users" 
    onchange="javascript:show_user()">
    <option>choose</option>
    %s
    </select>""" % (select)
        return most_active_user, select, active_users

    @staticmethod
    def alt_stream_js(request):
        """Temporarily here to keep assets contained in the module."""
        from pyramid.response import Response
        js = """
     function show_user() {
       var select = document.getElementsByName('active_users')[0];
       var i = select.selectedIndex;
       var user = select[i].value;
       location.href= '/stream.alt?by_url=no&user=' + user;
    } """
        r = Response(js)
        r.content_type = b'text/javascript'
        return r

    @staticmethod
    def alt_stream_template(args):
        """Temporarily here to consolidate assets in this file."""
        return u"""<html>
<head>
    <link rel="stylesheet" href="https://hypothes.is/assets/styles/app.min.css" /> 
    <link rel="stylesheet" href="https://hypothes.is/assets/styles/hypothesis.min.css" />
    <style>
    body {{ padding: 10px; font-size: 10pt; position:relative; margin-top: 2%; width:80%; margin-left: auto; margin-right:auto}}
    h1 {{ font-weight: bold; margin-bottom:10pt }}
    .stream-url {{ margin-top:3pt; word-wrap:break-word;  overflow:hidden; border-style: solid; border-color: rgb(179, 173, 173); border-width: thin; padding: 4px;}}
    .stream-reference {{ margin-bottom:4pt; /*margin-left:6%*/ }}
    .stream-annotation {{ /*margin-left: 3%; margin-bottom: 4pt; */}}
    .stream-text {{ margin-bottom: 2pt; /*margin-left:7%;*/ word-wrap: break-word }}
    .stream-tags {{ margin-bottom: 10pt; }}
    .stream-user {{ font-weight: bold; font-style:normal}}
    .user-sig {{ font-size:smaller }}
    .reply  {{ margin-top:10px; border-left: 1px dotted #969696; padding-left:10px }}
    .reply-1 {{ margin-left:2%; }}
    .reply-2 {{ margin-left:4%; }}
    .reply-3 {{ margin-left:6%; }}
    .reply-4 {{ margin-left:8%; }}
    .reply-5 {{ margin-left:10%; }}
    .stream-selector {{ float:right; }}
    .stream-picklist {{ font-size:smaller; float:right }}
    ul, li {{ display: inline }}
    li {{ color: #969696; font-size: smaller; border: 1px solid #d3d3d3; border-radius: 2px;}}
    img {{ max-width: 100% }}
    annotation-timestamp {{ margin-right: 20px }}
    img {{ padding:10px }}
    a.tag-item {{ text-decoration: none; border: 1px solid #BBB3B3; border-radius: 2px; padding: 3px; color: #969696; background: #f9f9f9; }}
    a.selected-tag-item {{ rgb(215, 216, 212); padding:3px; color:black; border: 1px solid black;}}
    .user-contributions: {{ clear:left }}
    .user-image-small {{ height: 20px; vertical-align:middle; margin-right:4px; padding:0 }}
    .other-users {{ font-size:smaller;font-style:italic }}
    .stream-active-users-widget {{ margin-top: 20px }}
    .paper {{ margin:15px; border-color:rgb(192, 184, 184); border-width:thin;border-style:solid }}
    </style>
</head>
<body class="ng-scope">
{head}
{main}
<script src="/stream.alt.js"></script>
</body>
</html> """.format(head=args['head'],main=args['main'])

    def make_indexes(self):
        while True:
            try:
                print 'updating'
                rows = HypothesisUtils().search_all()
                rows = list(rows)
                self.update_uri_users_dict(rows)
                self.update_anno_and_ref_and_photo_dicts(rows)
                self.update_user_annos(rows)
                time.sleep(15)
            except:
                print traceback.format_exc()
            
    def increment_index(self, idx, key):
        value = idx.get(key)
        if value is not None:
            value = int(value)
            value += 1
            idx.set(key,value)
        else:
            idx.set(key,1)

    def get_user_twitter_photo(self,user):
        generic = 'http://jonudell.net/h/generic-user-icon.jpg'
        r = requests.get('https://twitter.com/' + user)
        if r.status_code != 200:
            url = generic
        try:
            soup = BeautifulSoup(r.text, 'html.parser')
            img = soup.select('.ProfileAvatar-image')[0]
            url = img.attrs['src']
        except:
            url = generic
            print traceback.format_exc()
        print user, url
        return url

    def update_uri_users_dict(self,rows):
        for row in rows:
            raw = HypothesisRawAnnotation(row) 
            if self.uri_users.get(raw.uri) is None:
                self.uri_users.set(raw.uri, json.dumps([]))
            users = json.loads(self.uri_users.get(raw.uri))
            if raw.user not in users:
                users.append(raw.user)
                self.uri_users.set(raw.uri, json.dumps(users))
      
    def update_anno_and_ref_and_photo_dicts(self,rows):
        for row in rows:
            raw = HypothesisRawAnnotation(row) 
            id = raw.id
            user = raw.user
            refs = raw.references
            if self.anno_dict.get(id) == None:
                print 'adding %s to anno_dict' %  id 
                self.anno_dict.set(id, json.dumps(row))
                print 'incrementing anno count for %s' %  user
                self.increment_index(self.user_anno_counts, user)
                if len(refs):
                    print 'incrementing ref count for %s' %  user    
                    self.increment_index(self.user_replies, user)
                if self.user_icons.get(user) is None:
                    print 'adding photo for %s' %  user
                    self.user_icons.set(user, self.get_user_twitter_photo(user))

        for row in rows:
            raw = HypothesisRawAnnotation(row) 
            id = raw.id
            user = raw.user
            if len(raw.references):
                ref = raw.references[-1]
                try:
                    children_json = self.ref_children.get(ref)
                    if children_json is not None:
                        children = json.loads(children_json)
                    else:
                        children = []
                    if raw.id not in children:
                        print 'adding %s as child of %s for %s' % ( raw.id, ref, user) 
                        children.append(id)
                        self.ref_children.set(ref, json.dumps(children))           
                    self.ref_parents.set(id, ref)
                except:
                    print traceback.format_exc()
                    print 'id: ' + ref

    def update_user_annos(self,rows):
        for row in rows:
            raw = HypothesisRawAnnotation(row)
            user = raw.user
            annos_json = self.user_annos.get(user)
            if annos_json is None:
                annos = []
            else:
                annos = json.loads(annos_json)
            ids = [a['id'] for a in annos]
            if raw.id not in ids:
                print 'adding %s to %s' % ( row['id'], user) 
                annos.append(row)
                self.user_annos.set(user, json.dumps(annos))

    def create_timeline(self,counts, days):
        dataset = pd.DataFrame( { 'Day': pd.Series(days),
                                 'Counts': pd.Series(counts) } )
        sns.set_style("whitegrid")
        f, ax = plt.subplots(figsize=(8,4))
        ax.bar(dataset.index, dataset.Counts, width=.8, color="#278DBC", align="center")
        ax.set(xlim=(-1, len(dataset)))
        ax.xaxis.grid(False)
        ax.yaxis.grid(False)
        ax.set_xticks([])
        ax.set_yticks([])
        sns.despine(left=True)
        ram = cStringIO.StringIO()
        plt.savefig(ram,format='svg')
        plt.close()
        s = ram.getvalue()
        ram.close()
        s = re.sub('<svg[^<]+>', '<svg preserveAspectRatio="none" height="100%" version="1.1" viewBox="0 0 576 288" width="100%" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">', s)
        s = '<div style="width:100%;height:60px">' + s + '</div>'
        return s

    def make_timeline_data(self,user):
        annos = json.loads(self.user_annos.get(user))
        dates = [a['updated'] for a in annos]
        dates = [parser.parse(date) for date in dates]
        dates.sort()
        dates = dates
    
        first = dates[0]
        last = dates[-1]
    
        def perdelta(start, end, delta):
            curr = start
            while curr < end:
                yield curr.strftime('%Y-%m-%d')
                curr += delta
    
        day_dict = defaultdict(int)
        for date in dates:
            day = date.strftime('%Y-%m-%d')
            day_dict[day] += 1
    
        for day in perdelta(first, last, timedelta(days=1)):
            if day_dict.has_key(day) == False:
                day_dict[day] = 0
    
        days = day_dict.keys()
        days.sort()
        counts = [day_dict[day] for day in days]
        return counts, days

        
class HypothesisRawAnnotation:
    
    def __init__(self, row):
        """Encapsulate one row of a Hypothesis API search."""
        self.id = row['id']
        self.updated = row['updated'][0:19]
        self.user = row['user'].replace('acct:','').replace('@hypothes.is','')
        self.uri = row['uri'].replace('https://via.hypothes.is/h/','').replace('https://via.hypothes.is/','')

        if row['uri'].startswith('urn:x-pdf') and row.has_key('document'):
            if row['document'].has_key('link'):
                self.links = row['document']['link']
                for link in self.links:
                    self.uri = link['href']
                    if self.uri.encode('utf-8').startswith('urn:') == False:
                        break
            if self.uri.encode('utf-8').startswith('urn:') and row['document'].has_key('filename'):
                self.uri = row['document']['filename']

        if row.has_key('document') and row['document'].has_key('title'):
            t = row['document']['title']
            if isinstance(t, types.ListType) and len(t):
                self.doc_title = t[0]
            else:
                self.doc_title = t
        else:
            self.doc_title = self.uri
        self.doc_title = self.doc_title.replace('"',"'")
        if self.doc_title == '': self.doc_title = 'untitled'

        self.tags = []
        if row.has_key('tags') and row['tags'] is not None:
            self.tags = row['tags']
            if isinstance(self.tags, types.ListType):
                self.tags = [t.strip() for t in self.tags]

        self.text = ''
        if row.has_key('text'):
            self.text = row['text']

        self.references = []
        if row.has_key('references'):
            self.references = row['references']

        self.target = []
        if row.has_key('target'):
            self.target = row['target']

        self.is_page_note = False
        if self.references == [] and self.target == [] and self.tags == []: 
            self.is_page_note = True
        if row.has_key('document') and row['document'].has_key('link'):
            self.links = row['document']['link']
            if not isinstance(self.links, types.ListType):
                self.links = [{'href':self.links}]
        else:
            self.links = []


class HypothesisHtmlAnnotation:
    def __init__(self, h_stream, raw):
        self.quote_html = h_stream.make_quote_html(raw)
        self.text_html = h_stream.make_text_html(raw)
        self.tag_html = h_stream.make_tag_html(raw)
        self.raw=raw


class anno_dict:
    def __init__(self):
        pass

    def get(self, id):
        url = HypothesisUtils().api_url + '/annotations/' + id
        r = requests.get(url)
        try:
            return r.text
        except:
            print traceback.format_exc()
            return None

class ref_parents:
    def __init__(self):
        pass

    def get(self,id):
        url = HypothesisUtils().api_url + '/annotations/' + id
        r = requests.get(url)
        try:
            j = json.loads(r.text)
            if j.has_key('references'):
                return j['references'][-1]
            else:
                return None
        except:
            print traceback.format_exc()
            return None

class ref_children:
    def __init__(self):
        pass
    
    def get(self, id):
        params = { 'references':id }
        url = HypothesisUtils().query_url.format(query=urlencode(params))
        try:
            r = requests.get(url)
            j = json.loads(r.text)
            if len(j['rows']) == 0:
                return None
            children = []
            for row in j['rows']:
                child_id = row['id']
                grandchildren = self.get(child_id)
                if grandchildren is None:
                    children.append(child_id)
            return json.dumps(children) if len(children) else None
        except:
            print traceback.format_exc()
            return None

    """ 
    a sample link structure in an annotation

    "link": [
    {
        "href": "http://thedeadcanary.wordpress.com/2014/05/11/song-of-myself/"
    }, 
    {
        "href": "http://thedeadcanary.wordpress.com/2014/05/11/song-of-myself/", 
        "type": "", 
        "rel": "canonical"
    }, 
    """

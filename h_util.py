import requests, json, types, re, operator, traceback, thread, time, redis
from pyramid.response import Response
from datetime import datetime
from collections import defaultdict
from markdown import markdown
import urlparse

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

    def make_annotation_payload(self, url, start_pos, end_pos, prefix, quote, suffix, text, tags, link):
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

    def create_annotation(self, url=None, start_pos=None, end_pos=None, prefix=None, 
               quote=None, suffix=None, text=None, tags=None, link=None):
        """Call API with token and payload."""
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json;charset=utf-8' }
        payload = self.make_annotation_payload(url, start_pos, end_pos, prefix, quote, suffix, text, tags, link)
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

    @staticmethod
    def alt_stream_js(request):
        """Temporarily here to keep assets contained in the module."""
        from pyramid.response import Response
        js = """
     function show_user(by_url) {
       var select = document.getElementsByName('active_users')[0];
       var i = select.selectedIndex;
       var user = select[i].value;
       location.href= '/stream.alt?by_url=' + by_url + '&user=' + user;
    } """
        r = Response(js)
        r.content_type = b'text/javascript'
        return r

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
        self.user_annos = redis.StrictRedis(host=self.redis_host,port=6379, db=3) 
        self.user_replies = redis.StrictRedis(host=self.redis_host,port=6379, db=4) 
        #self.anno_dict = anno_dict()
        #self.ref_parents = ref_parents()
        #self.ref_children = ref_children()
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
            if updated < self.uri_updates[uri]:
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
                tag_html = '<a title="remove filter on this tag" href="%s">%s</a>' % ( url, row_tag )
            else:
                klass = "tag-item"
                tags.append(row_tag)
                url += '&tags=' + ','.join(tags)
                tag_html = '<a title="add filter on this tag" href="%s">%s</a>' % ( url, row_tag)
            tag_items.append('<li class="%s">%s</li>' % (klass, tag_html))
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
            h_stream.by_url='yes'
        user, picklist, userlist = h_stream.get_active_user_data(q)  
        if q.has_key('user'):
            user = q['user'][0]
            if user not in userlist:
                picklist = ''
        if h_stream.by_url=='yes':
            head = '<p class="stream-selector"><a href="/stream.alt?by_url=no">view recently active users</a></p>' 
            head += '<h1>urls recently annotated</h1>'
            body = h_stream.make_alt_stream(user=None, tags=tags)
        else:
            head = '<h1>%s has contributed %s annotations, of which %s were replies</h1>' % (user, h_stream.user_annos.get(user), h_stream.user_replies.get(user) )
            head += '<p class="stream-selector"><a href="/stream.alt?by_url=yes">view recently annotated urls</a></p>' 
            head += '<h1 class="stream-active-users-widget">urls recently annotated by {user} <span class="stream-picklist">{users}</span></h1>'.format(user=user, users=picklist)
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
        id = html_annotation.raw.id
        if self.anno_dict.exists(id) == False:
            return
        """Render an annotation's URI."""
        when = self.show_friendly_time(html_annotation.raw.updated)
        doc_title = html_annotation.raw.doc_title
        via_url = HypothesisUtils().via_url
        s = '<div class="stream-url">'
        if uri.startswith('http'):
            s += """<a target="_new" class="ng-binding" href="%s">%s</a> 
(<a title="use Hypothesis proxy" target="_new" href="%s/%s">via</a>)"""  % (uri, doc_title, via_url, uri)
        else:
            s += doc_title
        s += """<span class="annotation-timestamp small pull-right ng-binding ng-scope">%s</span>
</div>""" % when
        return s

    def make_html_annotation(self, html_annotation=None, level=None):
            """Assemble rendered parts of an annotation into one HTML element."""
            s = ''
        
            id = html_annotation.raw.id

            if level > 0:
                s += '<div id="%s" class="reply-%s">' % ( id, level )
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
            for i in range(len(html_annotations)):


                first = ( i == 0 )
                html_annotation = html_annotations[i]
                if html_annotation == '':
                    continue
                s += self.display_url(html_annotation, uri)  

                id = html_annotation.raw.id

                if self.debug: 
                    self.log += '%s, %s\n' % ( uri, id )

                s += '<div class="paper">'

                if self.ref_parents.get(id) is not None:   # if part of thread, display whole thread
                    id = self.find_thread_root(id)
               
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
    onchange="javascript:show_user('%s')">
    %s
    </select>""" % (self.by_url, select)
        return most_active_user, select, active_users

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
    .stream-url {{ margin-top: 12pt; margin-bottom: 4pt; overflow:hidde; border-style: solid; border-color: rgb(179, 173, 173); border-width: thin; padding: 4px;}}
    .stream-reference {{ margin-bottom:10pt; /*margin-left:6%*/ }}
    .stream-annotation {{ /*margin-left: 3%;*/ margin-bottom: 4pt; }}
    .stream-text {{ margin-bottom: 4pt; /*margin-left:7%;*/ word-wrap: break-word }}
    .stream-tags {{ margin-bottom: 10pt; }}
    .stream-user {{ font-weight: bold; margin-bottom: 4pt; font-style:normal}}
    .user-sig {{ font-size:smaller }}
    .reply-1 {{ margin-left:2%; margin-top:10px; border-left: 1px dotted #969696; padding-left:10px }}
    .reply-2 {{ margin-left:4%; margin-top:10px; border-left: 1px dotted #969696; padding-left:10px }}
    .reply-3 {{ margin-left:6%; margin-top:10px; border-left: 1px dotted #969696; padding-left:10px }}
    .reply-4 {{ margin-left:8%; margin-top:10px; border-left: 1px dotted #969696; padding-left:10px }}
    .reply-5 {{ margin-left:10%; margin-top:10px; border-left: 1px dotted #969696; padding-left:10px }}
    .tag-item {{ text-decoration: none; border: 1px solid #d3d3d3; border-radius: 2px; padding: 0 .4545em .1818em; color: #969696; background: #f9f9f9; }}
    .stream-selector {{ float:right; }}
    .stream-picklist {{ margin-left: 20pt }}
    .stream-active-users-widget {{ margin-top:0;}}
    ul, li {{ display: inline }}
    li {{ color: #969696; font-size: smaller; border: 1px solid #d3d3d3; border-radius: 2px; padding: 0 .4545em .1818em }}
    img {{ max-width: 100% }}
    annotation-timestamp {{ margin-right: 20px }}
    img {{ padding:10px }}
    a {{ word-wrap: break-word }}
    .selected-tag-item {{ background-color: lightgray }}
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
            print 'updating'
            self.update_anno_and_ref_dicts()
            print 'sleeping'
            time.sleep(60 * 2)

    def increment_index(self, idx, key):
        value = int(idx.get(key))
        value += 1
        idx.set(key,value)

    def update_anno_and_ref_dicts(self):
        
        for row in HypothesisUtils().search_all():
            raw = HypothesisRawAnnotation(row) 
            id = raw.id
            user = raw.user
            refs = raw.references
            if self.anno_dict.get(id) == None:
                self.anno_dict.set(id, json.dumps(row))
                self.increment_index(self.user_annos, user)
                if len(refs):
                    self.increment_index(self.user_replies, user)
                print 'new: ' + id

        for row in HypothesisUtils().search_all():
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
                        children.append(id)
                        self.ref_children.set(ref, json.dumps(children))           
                    self.ref_parents.set(id, ref)
                except:
                    print traceback.format_exc()
                    print 'id: ' + ref
        
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

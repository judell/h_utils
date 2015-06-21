import requests, json, types, re, operator, traceback
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

    def __init__(self, username=None, password=None):
        self.app_url = 'https://hypothes.is/app'
        self.api_url = 'https://hypothes.is/api'
        self.query_url = 'https://hypothes.is/api/search?{query}'
        self.anno_url = 'https://hypothes.is/a'
        self.via_url = 'https://via.hypothes.is'
        self.username = username
        self.password = password

    def login(self):
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

    def search_all(self):
        params = {'limit':200, 'offset':0 }
        while True:
            h_url = self.query_url.format(query=urlencode(params))
            r = requests.get(h_url).json()
            rows = r.get('rows')
            params['offset'] += len(rows)
            if len(rows) is 0:
                break
            for row in rows:
                yield row

    """ 
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

    def make_annotation_payload(self, url, start_pos, end_pos, prefix, quote, suffix, text, tags, link):
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
        headers = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json;charset=utf-8' }
        payload = self.make_annotation_payload(url, start_pos, end_pos, prefix, quote, suffix, text, tags, link)
        data = json.dumps(payload, ensure_ascii=False)
        r = requests.post(self.api_url + '/annotations', headers=headers, data=data)
        return r

    def call_search_api(self, args={'limit':200}):
        h_url = self.query_url.format(query=urlencode(args))
        json = requests.get(h_url).json()
        return json

    def get_active_users(self):
        j = self.call_search_api()
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
    def init_tag_url(limit=None, selected_user=None, by_url=None):
        url = '/stream.alt?user='
        if selected_user is not None:
            url += selected_user
        url += '&by_url='
        if by_url == 'yes':
            url += 'yes'
        url += '&limit='
        if limit is not None:
            url += str(limit)
        return url

    @staticmethod
    def make_tag_html(raw, limit=None, selected_user=None, selected_tags=None, by_url=None):

        row_tags = raw.tags
        if len(row_tags) == 0:
            return ''
        if selected_tags is None:
            selected_tags = ()

        tag_items = []
        for row_tag in row_tags:
            url = HypothesisUtils.init_tag_url(limit=limit, selected_user=selected_user, by_url=by_url)
            if row_tag in selected_tags:
                klass = "selected-tag-item"
                tags = list(selected_tags)
                tags.remove(row_tag)
                url += '&tags=' + ','.join(tags)
                tag_html = '<a title="remove filter on this tag" href="%s">%s</a>' % ( url, row_tag )
            else:
                klass = "tag-item"
                tags = list(selected_tags)
                tags.append(row_tag)
                url += '&tags=' + ','.join(tags)
                tag_html = '<a title="add filter on this tag" href="%s">%s</a>' % ( url, row_tag)
            tag_items.append('<li class="%s">%s</li>' % (klass, tag_html))
        return '<ul>%s</ul>' % '\n'.join(tag_items)

    @staticmethod
    def make_quote_html(raw):
        quote = ''
        target = raw.target
        try:
          if target is None:
              return quote 
          if isinstance(target,types.ListType) and len(target) == 0:
              return quote
          dict = {}
          if isinstance(target,types.ListType) and len(target) > 0:
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

    @staticmethod
    def make_text_html(raw):
        text = raw.text
        if raw.is_page_note:
            text = '<span title="Page Note" class="h-icon-insert-comment"></span> ' + text
        text = markdown(text)
        return text

    @staticmethod
    def make_references_html(raw):
        anno_url = HypothesisUtils().anno_url
        references = raw.references
        if references is None or len(references) == 0:
            return ''
        assert( isinstance(references,types.ListType) )
        ref = references[0]
        html = """
<a onclick="javascript:embed_conversation('{ref}'); return false"  
   id="{ref}" 
   target="_new" 
   href="{anno_url}/{ref}">conversation</a>"""
        ref_html = html.format(anno_url=anno_url, ref=ref)
        return ref_html

    @staticmethod
    def alt_stream_js(request):
        from pyramid.response import Response
        js = """
    function embed_conversation(id) {
        element = document.getElementById(id);
        element.outerHTML = '<iframe height="300" width="85%" src="https://hypothes.is/a/' + id + '"/>'
        return false;
    }

    function show_user() {
       var select = document.getElementsByName('active_users')[0];
       var i = select.selectedIndex;
       var user = select[i].value;
       location.href= '/stream.alt?user=' + user;
    } """
        r = Response(js)
        r.content_type = b'text/javascript'
        return r

class HypothesisStream:

    def __init__(self, limit=None):
        self.uri_html_annotations = defaultdict(list)
        self.uri_updates = {}
        self.uris_by_recent_update = []
        self.uri_references = {}
        self.limit = limit
        self.conversations = {}

    def add_row(self, row, selected_user=None, selected_tags=None, by_url=None):
        raw = HypothesisRawAnnotation(row)
        if len(raw.references):
            ref = raw.references[0]
            self.conversations[ref] = HypothesisHtmlAnnotation(self.limit, by_url, raw, selected_tags, selected_user)
            return

        uri = raw.uri
        updated = raw.updated
        if self.uri_updates.has_key(uri) == True:  # track most-recent update per uri
            if updated < self.uri_updates[uri]:
                self.uri_updates[uri] = updated
        else:
            self.uri_updates[uri] = updated

        html_annotation = HypothesisHtmlAnnotation(self.limit, by_url, raw, selected_tags, selected_user)
        self.uri_html_annotations[uri].append( html_annotation )

    def sort(self):
        sorted_uri_updates = sorted(self.uri_updates.items(), key=operator.itemgetter(1), reverse=True)
        for update in sorted_uri_updates:
            self.uris_by_recent_update.append( update[0] )

    @staticmethod
    def get_active_user_data(q):
        if q.has_key('user'):
            user = q['user'][0]
            user, picklist, userlist = HypothesisStream.format_active_users(user=user)
        else:
            user, picklist, userlist = HypothesisStream.format_active_users(user=None)
        userlist = [x[0] for x in userlist]
        return user, picklist, userlist

    @staticmethod
    def alt_stream(request):
        limit = 200
        q = urlparse.parse_qs(request.query_string)
        user, picklist, userlist = HypothesisStream.get_active_user_data(q)  
        h_stream = HypothesisStream(limit)
        if q.has_key('tags'):
            tags = q['tags'][0].split(',')
            tags = [t.strip() for t in tags]
            tags = tuple(tags)
        else:
            tags = None
        if q.has_key('by_url'):
            by_url=q['by_url'][0]
        else:
            by_url=None
        if q.has_key('user'):
            user = q['user'][0]
            if user not in userlist:
                picklist = ''
        if by_url=='yes':
            head = '<p class="stream-selector"><a href="/stream.alt?limit=%s">view recently active users</a></p>' % limit
            head += '<h1>urls recently annotated</h1>'
            body = h_stream.make_alt_stream(user=None, tags=tags, by_url=by_url, limit=limit)
        else:
            head = '<p class="stream-selector"><a href="/stream.alt?limit=%s&by_url=yes">view recently annotated urls</a></p>' % limit
            head += '<h1 class="stream-active-users-widget">urls recently annotated by {user} <span class="stream-picklist">{users}</span></h1>'.format(user=user, users=picklist)
            body = h_stream.make_alt_stream(user=user, tags=tags, by_url=by_url, limit=limit)
        html = HypothesisStream.alt_stream_template( {'head':head,  'main':body} )
        return Response(html.encode('utf-8'))

    def display_url(self, html_annotation, uri):
        dt_str = html_annotation.raw.updated
        dt = datetime.strptime(dt_str[0:16], "%Y-%m-%dT%H:%M")
        when = HypothesisUtils.friendly_time(dt)
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

    def display_html_annotation(self, html_annotation, by_url, first, uri, is_reply=None):
            s = ''
            if first:
                s = self.display_url(html_annotation, uri)
        
            if is_reply:
                s += '<div class="stream-reply">'
            else:
                s += '<div class="paper stream-annotation">'

            #s += '<p>' + html_annotation.raw.id + '</p>'
        
            if by_url == 'yes':
                user = html_annotation.raw.user
                s += '<p class="stream-user"><a href="/stream.alt?user=%s">%s</a></p>' % (user, user)
           
            quote_html = html_annotation.quote_html
            text_html = html_annotation.text_html
            tag_html = html_annotation.tag_html
        
            is_page_note = html_annotation.raw.is_page_note
        
            if quote_html != '':
                s += """<p class="annotation-quote">%s</p>"""  % quote_html
        
            if text_html != '' and references_html == '':
                s += """<p class="stream-text">%s</p>""" %  (text_html)
        
            if tag_html != '':
                s += '<p class="stream-tags">%s</p>' % tag_html
        
            annotation_id = html_annotation.raw.id
            if self.conversations.has_key(annotation_id):
                anno = self.conversations[annotation_id]
                s += self.display_html_annotation(anno, by_url, False, uri, is_reply=True)

            s += '</div>'

            return s

    def make_alt_stream(self, user=None, tags=None, by_url=None, limit=None):
        if limit is None:
            limit = 200
        bare_search_url = '%s/search?limit=%s' % ( HypothesisUtils().api_url, limit )
        parameterized_search_url = bare_search_url

        if user is not None:
            parameterized_search_url += '&user=' + user

        if tags is not None:
            for tag in tags:
                parameterized_search_url += '&tags=' + tag

        response = requests.get(parameterized_search_url)

        rows = response.json()['rows']

        unique_urls = set()
        for row in rows:
            unique_urls.add(row['uri'])

        for row in rows:
           self.add_row(row, selected_user=user, selected_tags=tags, by_url=by_url)
        self.sort()

        s = ''
        for uri in self.uris_by_recent_update:
            html_annotations = self.uri_html_annotations[uri]

            for i in range(len(html_annotations)):
                first = ( i == 0 )
                html_annotation = html_annotations[i]
                s += self.display_html_annotation(html_annotation, by_url, first, uri)
        return s

    @staticmethod        
    def format_active_users(user=None):
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
    %s
    </select>""" % select
        return most_active_user, select, active_users

    @staticmethod
    def alt_stream_template(args):
        return u"""<html>
<head>
    <link rel="stylesheet" href="https://hypothes.is/assets/styles/app.min.css" /> 
    <link rel="stylesheet" href="https://hypothes.is/assets/styles/hypothesis.min.css" />
    <style>
    body {{ padding: 10px; font-size: 10pt; position:relative}}
    h1 {{ font-weight: bold; margin-bottom:10pt }}
    .stream-url {{ margin-top: 12pt; margin-bottom: 4pt; overflow:hidde; border-style: solid; border-color: rgb(179, 173, 173); border-width: thin; padding: 4px;}}
    .stream-reference {{ margin-bottom:10pt; /*margin-left:6%*/ }}
    .stream-annotation {{ /*margin-left: 3%;*/ margin-bottom: 4pt; }}
    .stream-text {{ margin-bottom: 4pt; /*margin-left:7%;*/ word-wrap: break-word }}
    .stream-tags {{ margin-bottom: 10pt; }}
    .stream-user {{ font-weight: bold; margin-bottom: 4pt; font-style:normal}}
    .stream-reply {{ margin-left:2%; margin-top:10px; border-left: 1px dotted #969696; padding-left:10px }}
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

class HypothesisRawAnnotation:
    
    def __init__(self, row):
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
    def __init__(self, limit, by_url, raw, selected_tags, selected_user):
        self.quote_html = HypothesisUtils.make_quote_html(raw)
        self.text_html = HypothesisUtils.make_text_html(raw)
        self.tag_html = HypothesisUtils.make_tag_html(raw, limit=limit, selected_user=selected_user, selected_tags=selected_tags, by_url=by_url)
        self.raw=raw


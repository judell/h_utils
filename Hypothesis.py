import requests,json,types
from datetime import datetime

try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode


class Hypothesis:

    def __init__(self, username=None, password=None):
        self.app_url = 'https://hypothes.is/app'
        self.api_url = 'https://hypothes.is/api'
        self.username = username
        self.password = password

    def login(self):
        # https://github.com/rdhyee/hypothesisapi 
        # pick up some cookies to start the session
        
        r = requests.get(self.app_url)
        cookies = r.cookies

        # make call to https://hypothes.is/app?__formid__=login
        
        payload = {"username":self.username,"password":self.password}
        self.csrf_token = cookies['XSRF-TOKEN']
        data = json.dumps(payload)
        headers = {'content-type':'application/json;charset=UTF-8', 'x-csrf-token': self.csrf_token}
        
        r = requests.post(url=self.app_url  + "?__formid__=login", data=data, cookies=cookies, headers=headers)
        
        # get token

        url = self.api_url + "/token?" + urlencode({'assertion':self.csrf_token})
        r = (requests.get(url=url,
                         cookies=cookies, headers=headers))
      
        self.token =  r.content

    def search(self):
        params = {'limit':200, 'offset':0 }

        while True:
            h_url = 'https://hypothes.is/api/search?{query}'.format(query=urlencode(params))
            r = requests.get(h_url).json()
            rows = r.get('rows')
            params['offset'] += len(rows)
            if len(rows) is 0:
                break
            for row in rows:
                yield row

    def create(self, url=None, start_pos=None, end_pos=None, prefix=None, quote=None, suffix=None, text=None, tags=None):
        headers = {'Authorization': 'Bearer ' + self.token}
        payload = {
            "uri": url,
            "user": 'acct:' + self.username + '@hypothes.is',
            "permissions": {
                "read": ["group:__world__"],
                "update": ['acct:' + self.username + '@hypothes.is'],
                "delete": ['acct:' + self.username + '@hypothes.is'],
                "admin":  ['acct:' + self.username + '@hypothes.is']
                },
            "document": { },
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
        data = json.dumps(payload)
        r = requests.post(self.api_url + '/annotations', headers=headers, data=data)
        return r

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
    def get_info_from_row(r):
        user = r['user'].replace('acct:','').replace('@hypothes.is','')
        uri = r['uri']
        if r['uri'].startswith('urn:x-pdf') and r.has_key('document'):
            if r['document'].has_key('link'):
                uri = r['document']['link'][-1]['href']
        if r.has_key('document') and r['document'].has_key('title'):
            t = r['document']['title']
            if isinstance(t, types.ListType) and len(t):
                doc_title = t[0]
            else:
                doc_title = t
        else:
            doc_title = uri
        doc_title = doc_title.replace('"',"'")
        if r.has_key('tags'):
            tags = r['tags']
            if isinstance(tags, types.ListType):
                tags = [t.strip() for t in tags]
            else:
                tags = []
        text = ''
        if r.has_key('text'):
            text = r['text']
        return { 'user':user, 'uri':uri, 'doc_title':doc_title, 'tags':tags, 'text':text }

 



    

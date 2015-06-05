import requests,json, types

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

    @staticmethod
    def get_user_uri_doctitle_from_row(r):
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
        return { 'user':user, 'uri':uri, 'doc_title':doc_title }

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

if __name__ == '__main__':
    h = Hypothesis('judell','*****')
    h.login()
    r = h.create(url='http://jonudell.net', 
                    prefix= 'This page', 
                    quote= 'collects pointers to', 
                    suffix= 'writing, software, audio, and video.', 
                    text= 'test annotation', 
                    tags= ['test','tag']
                    )

    print r.status_code


    

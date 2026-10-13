"""Free local vision inference through Ollama; no remote fallback or API key."""
import base64
import json
import re
import urllib.error
import urllib.request

from .ai_planner import SYSTEM


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        raise RuntimeError('Local AI tried to redirect outside its local endpoint. Request stopped.')


def local_request(path,payload=None,timeout=5):
    # Do not route screenshots through an inherited Internet proxy.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    data=json.dumps(payload).encode() if payload is not None else None
    request=urllib.request.Request('http://127.0.0.1:11434/api/'+path,data=data,
                                  headers={'Content-Type':'application/json'})
    try:
        with opener.open(request,timeout=timeout) as response:
            return json.loads(response.read(2_000_000))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f'Ollama request failed (HTTP {exc.code}). Check the model is installed and supports images.') from None
    except urllib.error.URLError:
        raise RuntimeError('Could not reach local Ollama. Open the Ollama app on this computer and try again.') from None


def check_local(model='gemma3:4b'):
    if not re.fullmatch(r'[A-Za-z0-9._/:+\-]{1,100}',model) or 'cloud' in model.lower():
        raise ValueError('Choose a locally installed vision model, not an Ollama cloud model.')
    models=local_request('tags').get('models',[])
    if not any(model in (m.get('name'),m.get('model')) for m in models):
        raise ValueError(f'Local model {model} is not installed. Run Prepare Free AI Mac.command or install it in Ollama.')
    metadata=local_request('show',{'model':model})
    if metadata.get('remote_host') or metadata.get('remote_model'):
        raise ValueError('Remote/cloud-backed Ollama models are disabled in free local mode.')
    capabilities=metadata.get('capabilities',[])
    if capabilities and 'vision' not in capabilities:
        raise ValueError('This model does not support screenshots. Choose a local vision model such as gemma3:4b.')


def compact(snapshot):
    result={k:v for k,v in snapshot.items() if k!='elements'}
    elements=[e for e in snapshot['elements'] if e.get('on_screen',True) or e.get('store_context')]
    result['elements']=[{k:v for k,v in e.items() if k in (
        'id','tag','role','type','text','label','control','selected','options','store_context','value')}
        for e in elements[:100]]
    result['observation_limited']=len(elements)>100
    return result


class LocalVisionPlanner:
    def __init__(self,model='gemma3:4b'):
        self.model=model
        self.calls=self.input_tokens=self.output_tokens=0

    def decide(self,store,snapshot,screenshot,history,last_error=''):
        context={'store_address':store.address,'channel':store.channel,'page':compact(snapshot),
                 'recent_actions':history[-5:],'last_error':last_error}
        payload={'model':self.model,'stream':False,'format':'json',
                 'options':{'temperature':0,'num_ctx':16384,'num_predict':2000},
                 'messages':[{'role':'system','content':SYSTEM},
                             {'role':'user','content':json.dumps(context),
                              'images':[base64.b64encode(screenshot).decode()]}]}
        self.calls+=1
        result=local_request('chat',payload,timeout=180)
        self.input_tokens+=result.get('prompt_eval_count',0)
        self.output_tokens+=result.get('eval_count',0)
        try:
            decision=json.loads(result['message']['content'])
        except (KeyError,ValueError,TypeError):
            raise ValueError('Local AI did not return a valid browser action') from None
        if not isinstance(decision,dict):
            raise ValueError('Local AI response must be one action object')
        return decision

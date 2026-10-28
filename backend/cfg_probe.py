import sys, json
sys.path.insert(0,'/home/claude/c-cfg-analyzer/backend')
from cfg_analyzer.analyzer import analyze_source
from cfg_analyzer.validation import validate_request
def run(src, **kw):
    return analyze_source(validate_request({"source":src, **kw}))
def show(src, **kw):
    r=run(src, **kw)
    g=r['graph']
    for n in g['nodes']: print(n['id'], n['kind'], n['role'], repr(n['label'])[:50], 'R' if n['reachable'] else 'DEAD')
    for e in g['edges']: print(' ',e['id'],e['source'],'->',e['target'],e['label'],'(back)' if e['back_edge'] else '')
    c=r['complexity']; print(c['substituted'], '| branch', c['branch_substituted'], '| struct', c['structural']['value'], c['structural']['agrees'])
    print('paths', r['paths']['status'], r['paths']['rank'], '/', r['paths']['expected'])
    for w in r['warnings']: print('W', w['severity'], w['code'], w['message'][:80])
    return r
if __name__=="__main__":
    show(sys.argv[1])

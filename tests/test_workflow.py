import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

CLI=Path(__file__).resolve().parents[1]/'src/pocket_studio/cli.py'

class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'film'
        self.call('init',str(self.root),'--title','test')
        manifest=json.loads((self.root/'motion.json').read_text());manifest['format']={'width':320,'height':180,'fps':24}
        (self.root/'motion.json').write_text(json.dumps(manifest))

    def call(self,*args,success=True):
        p=subprocess.run([sys.executable,str(CLI),'--json',*args],text=True,capture_output=True,cwd='/tmp')
        self.assertEqual(p.returncode==0,success,p.stdout+p.stderr)
        return json.loads(p.stdout)

    def spec(self,name,data):
        p=Path(self.tmp.name)/name;p.write_text(json.dumps(data));return str(p)

    def rendered(self):
        spec=self.spec('render.json',{'label':'fixture','argv':['ffmpeg','-v','error','-y','-f','lavfi','-i','testsrc2=size=320x180:rate=24','-t','1','-c:v','libx264','-pix_fmt','yuv420p','{output}']})
        return self.call('render','--project',str(self.root),'--spec',spec)['data']

    def test_end_to_end_and_stale_review(self):
        item=self.rendered()
        cut=self.spec('cut.json',{'clips':[{'path':item['path'],'in':.1,'duration':.6}]})
        out=self.call('assemble','--project',str(self.root),'--spec',cut)['data']
        self.assertAlmostEqual(out['duration'],.6,delta=.1)
        page=self.call('review','--project',str(self.root))['data']
        self.assertEqual(page['artifacts'],2)
        fb=self.spec('feedback.json',{'id':out['id'],'sha256':out['sha256'],'author':'human','decision':'revise','time':.2,'note':'test fixture feedback'})
        self.call('feedback','--project',str(self.root),'--file',fb)
        with open(self.root/out['path'],'ab') as f:f.write(b'changed')
        self.call('feedback','--project',str(self.root),'--file',fb,success=False)

    def test_import_is_data_and_deduplicates(self):
        source=Path(self.tmp.name)/'danger.sh';source.write_text('touch SHOULD_NOT_EXIST')
        a=self.call('source','add',str(source),'--project',str(self.root))['data']
        b=self.call('source','add',str(source),'--project',str(self.root))['data']
        self.assertEqual(a['id'],b['id']);self.assertFalse((self.root/'SHOULD_NOT_EXIST').exists())

    def test_bad_trim_and_path_escape(self):
        item=self.rendered()
        for clip in [{'path':item['path'],'duration':20},{'path':'../../outside.mp4'}]:
            spec=self.spec('bad.json',{'clips':[clip]})
            self.call('assemble','--project',str(self.root),'--spec',spec,success=False)
        self.assertEqual(self.call('inspect','--project',str(self.root))['data']['cuts'],[])

    def test_failed_render_preserves_logs(self):
        spec=self.spec('fail.json',{'argv':[sys.executable,'-c','import sys;sys.exit(2)','{output}']})
        self.call('render','--project',str(self.root),'--spec',spec,success=False)
        self.assertEqual(self.call('inspect','--project',str(self.root))['data']['renders'],[])
        self.assertEqual(len(list((self.root/'renders').glob('*/stderr.log'))),1)

if __name__=='__main__':unittest.main()

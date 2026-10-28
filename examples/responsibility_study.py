"""Procedural 3D adapter study. Requires Pillow. No model/provider calls.
Illustrative retained responsibilities and selective activation; not measured data.
"""
import argparse
import math
import subprocess
from PIL import Image, ImageDraw, ImageFont

p=argparse.ArgumentParser(); p.add_argument('--output',required=True); a=p.parse_args()
W,H,FPS,SECONDS=960,540,24,6
font=ImageFont.load_default()
proc=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','-','-an','-c:v','libx264','-crf','18','-pix_fmt','yuv420p',a.output],stdin=subprocess.PIPE)

def ease(t):
    t=max(0,min(1,t));return t*t*(3-2*t)

for frame in range(FPS*SECONDS):
    t=frame/FPS
    yaw=.56+.20*math.sin(t*.4)
    def project(v):
        x,y,z=v
        xx=x*math.cos(yaw)-z*math.sin(yaw)
        zz=x*math.sin(yaw)+z*math.cos(yaw)
        depth=12+zz*.85-y*.4
        return (W/2+xx*750/depth,H*.53+(zz*.48-y)*750/depth)
    im=Image.new('RGB',(W,H),'#eeece7');d=ImageDraw.Draw(im)
    for k in range(-6,7):
        d.line([project((k,0,-5)),project((k,0,5))],fill='#d8d6d0',width=1)
        d.line([project((-5,0,k)),project((5,0,k))],fill='#d8d6d0',width=1)
    objects=[]
    active=(t*2.1)%25
    for row in range(5):
        for col in range(5):
            idx=row*5+col; x=(col-2)*1.18;z=(row-2)*1.18
            entrance=ease((t-idx*.022)/.9)
            pulse=math.exp(-((idx-active)/1.35)**2)*ease(t-1)
            height=(.23+.78*pulse)*entrance
            s=.44
            vertices=[(x-s,0,z-s),(x+s,0,z-s),(x+s,0,z+s),(x-s,0,z+s),
                      (x-s,height,z-s),(x+s,height,z-s),(x+s,height,z+s),(x-s,height,z+s)]
            color=(230,92,28) if pulse>.2 else (104,113,118)
            objects.append((x*math.sin(yaw)+z*math.cos(yaw),vertices,color))
    for _,vs,c in sorted(objects,reverse=True):
        for face,light in [([0,1,5,4],.68),([1,2,6,5],.85),([4,5,6,7],1.15)]:
            fill=tuple(min(255,int(v*light)) for v in c)
            d.polygon([project(vs[i]) for i in face],fill=fill)
    d.text((32,26),'POCKET STUDIO / MOTION STUDY',font=font,fill='#323536')
    d.text((32,H-40),'Persistent responsibilities. Selective activation.',font=font,fill='#323536')
    d.text((W-280,H-40),'Illustrative choreography / technical sample',font=font,fill='#646b6d')
    proc.stdin.write(im.tobytes())
proc.stdin.close()
if proc.wait(): raise SystemExit('FFmpeg failed')

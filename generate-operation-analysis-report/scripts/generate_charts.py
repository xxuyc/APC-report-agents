#!/usr/bin/env python3
import argparse
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from common import read_json

COLORS=['#2878B5','#9AC9DB','#F8AC8C','#C82423','#FF8884','#8ECFC9','#FFBE7A']
FONT_PATHS=[
    os.getenv('APC_REPORT_FONT',''),
    r'C:\Windows\Fonts\msyh.ttc',
    r'C:\Windows\Fonts\simhei.ttf',
    '/System/Library/Fonts/PingFang.ttc',
    '/System/Library/Fonts/STHeiti Medium.ttc',
    '/System/Library/Fonts/Supplemental/Arial Unicode.ttf',
]
def font(size,bold=False):
    paths=[r'C:\Windows\Fonts\msyhbd.ttc','/System/Library/Fonts/PingFang.ttc']+FONT_PATHS if bold else FONT_PATHS
    for p in paths:
        if p and Path(p).exists(): return ImageFont.truetype(p,size)
    try: return ImageFont.truetype('DejaVuSans.ttf',size)
    except OSError: pass
    return ImageFont.load_default()
def txt(draw,xy,value,size=22,fill='#333333',anchor=None,bold=False): draw.text(xy,str(value),font=font(size,bold),fill=fill,anchor=anchor)
def rotated_txt(image,xy,value,size=18,fill='#333333'):
    f=font(size); box=f.getbbox(str(value)); layer=Image.new('RGBA',(box[2]-box[0]+12,box[3]-box[1]+12),(255,255,255,0)); ld=ImageDraw.Draw(layer); ld.text((6,6),str(value),font=f,fill=fill)
    layer=layer.rotate(90,expand=True); image.paste(layer,(int(xy[0]-layer.width/2),int(xy[1]-layer.height/2)),layer)
def line_chart(image,draw,box,series,periods,color,unit,axis_policy='zero_baseline'):
    x0,y0,x1,y1=box; vals=[v for v in series if v is not None]
    if not vals: return
    lo,hi=min(vals),max(vals); raw_span=hi-lo or max(abs(hi),1)
    if axis_policy == 'zero_baseline':
        lo=0; hi=hi*1.10 if hi > 0 else 1
    else:
        lo=max(0,lo-raw_span*.12); hi=hi+raw_span*.12
    span=hi-lo or 1
    left,right,top,bottom=86,20,20,58; px0,px1=x0+left,x1-right; py0,py1=y0+top,y1-bottom
    for j in range(5):
        ratio=j/4; y=py1-(py1-py0)*ratio; value=lo+span*ratio
        draw.line((px0,y,px1,y),fill='#DCE3E9',width=1); txt(draw,(px0-10,y),f'{value:.2f}',15,'#52606D',anchor='rm')
    draw.line((px0,py1,px1,py1),fill='#52606D',width=2); draw.line((px0,py0,px0,py1),fill='#52606D',width=2)
    pts=[]
    for i,v in enumerate(series):
        if v is None: continue
        x=px0+(px1-px0)*i/max(1,len(series)-1); y=py1-(py1-py0)*(v-lo)/span; pts.append((x,y))
    if len(pts)>1: draw.line(pts,fill=color,width=4)
    for x,y in pts: draw.ellipse((x-4,y-4,x+4,y+4),fill=color)
    for i,m in enumerate(periods):
        x=px0+(px1-px0)*i/max(1,len(periods)-1); draw.line((x,py1,x,py1+5),fill='#52606D',width=1); txt(draw,(x,py1+10),m[5:]+'月',13,'#52606D',anchor='ma')
    txt(draw,((px0+px1)/2,y1-4),'月份',16,'#333333',anchor='ms'); rotated_txt(image,(x0+18,(py0+py1)/2),f'数值（{unit}）',16,'#333333')
def monthly(spec,out):
    chart=next(x for x in spec['charts'] if x['chart_id']=='monthly-trends'); charts=chart['series']; rows=max(1,(len(charts)+1)//2)
    W,H=2000,105+rows*405+55; img=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(img); txt(d,(W/2,38),spec.get('monthly_title','月度处理水量及进水水质年内变化'),36,'#1F4E78','ma',True)
    for i,s in enumerate(charts):
        row,col=divmod(i,2); x=45+col*985; y=105+row*405; txt(d,(x+480,y),s['title'],23,'#1F4E78',anchor='ma',bold=True); line_chart(img,d,(x,y+25,x+930,y+385),s['values'],spec['periods'],COLORS[i%len(COLORS)],s['unit'],chart.get('axis_policy','zero_baseline'))
    img.save(out/'monthly-trends.png',quality=95,dpi=(180,180))
def cost(spec,out):
    item=next(x for x in spec['charts'] if x['chart_id']=='cost-share'); values=[x['cost_cny'] for x in item['items']]; labels=[x['label'] for x in item['items']]
    W,H=1400,850; img=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(img); txt(d,(W/2,35),item['scope']+'构成',34,'#1F4E78','ma',True); total=sum(values)
    if not values:
        txt(d,(W/2,H/2),'源文件未提供货币成本数据',30,'#52606D','mm',True)
    elif item['type']=='pie' and total:
        box=(90,120,760,790); start=-90
        for i,v in enumerate(values):
            end=start+360*v/total; d.pieslice(box,start,end,fill=COLORS[i%len(COLORS)],outline='white',width=3); start=end
        for i,(label,v) in enumerate(zip(labels,values)):
            y=180+i*82; d.rectangle((840,y,875,y+28),fill=COLORS[i%len(COLORS)]); txt(d,(895,y-2),f'{label}  {v:,.2f} 元（{v/total*100:.1f}%）',22)
    else:
        maximum=max(values) if values else 1
        for i,(label,v) in enumerate(sorted(zip(labels,values),key=lambda x:x[1],reverse=True)):
            y=150+i*85; txt(d,(80,y),label,22); d.rectangle((300,y,300+900*v/maximum,y+42),fill=COLORS[i%len(COLORS)]); txt(d,(320+900*v/maximum,y),f'{v:,.0f}',20)
    img.save(out/'cost-share.png',quality=95,dpi=(180,180))
def yoy(spec,out):
    item=next((x for x in spec['charts'] if x['chart_id']=='yoy-change'),None)
    if not item: return
    rows=[x for x in item.get('items',[]) if x.get('change_pct') is not None]
    W,H=1500,950; img=Image.new('RGB',(W,H),'white'); d=ImageDraw.Draw(img); txt(d,(W/2,35),'2026年上半年主要指标同比变化',34,'#1F4E78','ma',True)
    if not rows:
        txt(d,(W/2,H/2),'无可比数据',28,'#52606D','mm'); img.save(out/'yoy-change.png',dpi=(180,180)); return
    vals=[x['change_pct'] for x in rows]; lo=min(min(vals),0); hi=max(max(vals),0); span=hi-lo or 1
    left,right,top,bottom=300,90,110,80; x0,x1=left,W-right; zero=x0+(0-lo)/span*(x1-x0)
    d.line((zero,top,zero,H-bottom),fill='#52606D',width=2)
    row_h=(H-top-bottom)/len(rows)
    for i,x in enumerate(rows):
        y=top+i*row_h+row_h*.18; h=row_h*.58; value=x['change_pct']; end=x0+(value-lo)/span*(x1-x0); color='#C82423' if value>5 else '#2878B5' if value>=0 else '#55A868'
        txt(d,(left-24,y+h/2),x['label'],21,'#243447','rm'); d.rectangle((min(zero,end),y,max(zero,end),y+h),fill=color)
        if value<0: txt(d,(end+12,y+h/2),f'{value:+.1f}%',17,'white','lm',True)
        else: txt(d,(end+12,y+h/2),f'{value:+.1f}%',18,color,'lm',True)
    img.save(out/'yoy-change.png',quality=95,dpi=(180,180))
def main():
    p=argparse.ArgumentParser(); p.add_argument('--spec',required=True); p.add_argument('--output-dir',required=True); a=p.parse_args(); out=Path(a.output_dir); out.mkdir(parents=True,exist_ok=True); spec=read_json(a.spec); monthly(spec,out); cost(spec,out); yoy(spec,out)
if __name__=='__main__': main()

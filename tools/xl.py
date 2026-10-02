import zipfile,re,sys,xml.etree.ElementTree as ET
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
def load(path):
    z=zipfile.ZipFile(path)
    ss=[]
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns):
            ss.append(''.join(t.text or '' for t in si.iter('{%s}t'%ns['m'])))
    wb=ET.fromstring(z.read('xl/workbook.xml'))
    names=[s.get('name') for s in wb.find('m:sheets',ns)]
    files=sorted([n for n in z.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml',n)],key=lambda n:int(re.findall(r'\d+',n)[0]))
    out={}
    for name,f in zip(names,files):
        rows=[]
        for r in ET.fromstring(z.read(f)).iter('{%s}row'%ns['m']):
            row={}
            for c in r.findall('m:c',ns):
                col=re.match(r'[A-Z]+',c.get('r')).group()
                v=c.find('m:v',ns); t=c.get('t')
                if t=='s' and v is not None: val=ss[int(v.text)]
                elif t=='inlineStr': val=''.join(x.text or '' for x in c.iter('{%s}t'%ns['m']))
                else: val=v.text if v is not None else None
                row[col]=val
            rows.append(row)
        out[name]=rows
    return out
if __name__=='__main__':
    d=load(sys.argv[1])
    for n,rows in d.items():
        print('SHEET',n,len(rows))
        for r in rows[:6]: print(r)

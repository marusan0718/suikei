import numpy as np, re, json, math, subprocess
from pathlib import Path
from scipy.signal import butter, sosfilt
from scipy.io import wavfile

SR=24000
DUR=90.0
FADE=12.0
RAW_DUR=DUR+FADE
N=int(RAW_DUR*SR)
t=np.arange(N,dtype=np.float64)/SR
rng=np.random.default_rng(20261003)

INDEX_HTML=Path("index.html").read_text(encoding="utf-8")
_PAYLOADS=json.loads(re.search(r"const LAYER_PAYLOADS=(\[.*?\]);\nconst API=",INDEX_HTML,re.S).group(1))
import base64
LAYER_HTML=[base64.b64decode(p).decode("utf-8") for p in _PAYLOADS]
BASE=[0.295,0.525,0.108,0.395,0.175,0.380]

OUT=Path('homepod-audio'); OUT.mkdir(exist_ok=True)
STEMS=Path('.render-cache'); STEMS.mkdir(exist_ok=True)
for _p in STEMS.glob('layer*.npy'): _p.unlink()

def pan_gains(p):
    p=np.clip(p,-1,1)
    return math.sqrt((1-p)*.5), math.sqrt((1+p)*.5)

def sine_voice(freq, amp, pan=0.0, drift_hz=0.0, drift_cents=0.0, phase0=None):
    if phase0 is None: phase0=float(rng.uniform(0,2*np.pi))
    ph=2*np.pi*freq*t+phase0
    if drift_hz and drift_cents:
        dev=freq*math.log(2)/1200*drift_cents
        beta=dev/max(drift_hz,1e-5)
        ph += beta*np.sin(2*np.pi*drift_hz*t+phase0*.37)
    sig=np.sin(ph).astype(np.float32)
    if np.ndim(amp): sig*=np.asarray(amp,dtype=np.float32)
    else: sig*=np.float32(amp)
    l,r=pan_gains(pan)
    return np.stack((sig*l,sig*r),axis=1)

def add_tone_segment(track,start,dur,freq,amp,pan=0,power=1.7,drift_cents=0):
    a=max(0,int(start*SR)); b=min(N,int((start+dur)*SR))
    if b<=a:return
    m=b-a; x=np.linspace(0,1,m,endpoint=False,dtype=np.float64)
    env=(0.00025+amp*np.power(np.maximum(0,np.sin(np.pi*x)),power)).astype(np.float32)
    tt=np.arange(m,dtype=np.float64)/SR
    f=freq*(2**(drift_cents/1200))
    sig=np.sin(2*np.pi*f*tt+rng.uniform(0,2*np.pi)).astype(np.float32)*env
    l,r=pan_gains(pan); track[a:b,0]+=sig*l; track[a:b,1]+=sig*r

def simple_space(x, wet=.15, brightness=1.0):
    # cheap diffuse multi-tap stereo ambience; stable and loop-friendly
    y=x.copy()
    taps=[(.073,.28),(.137,.20),(.223,.14),(.347,.10),(.521,.07)]
    for j,(sec,g) in enumerate(taps):
        d=int(sec*SR)
        if d>=len(x):continue
        if j%2==0:
            y[d:,0]+=x[:-d,1]*wet*g
            y[d:,1]+=x[:-d,0]*wet*g*.95
        else:
            y[d:,0]+=x[:-d,0]*wet*g*.92
            y[d:,1]+=x[:-d,1]*wet*g
    if brightness<1:
        cutoff=700+brightness*2500
        sos=butter(2,cutoff/(SR/2),btype='low',output='sos')
        y[:,0]=sosfilt(sos,y[:,0]).astype(np.float32)
        y[:,1]=sosfilt(sos,y[:,1]).astype(np.float32)
    return y

def circularize(raw):
    d=int(DUR*SR); f=int(FADE*SR)
    out=raw[:d].copy()
    q=np.linspace(0,1,f,endpoint=False,dtype=np.float32)
    # end continuation fades out while beginning fades in at loop start
    tail=raw[d:d+f]
    out[:f]=tail*(1-q[:,None])+raw[:f]*q[:,None]
    return out

def save_stem(i,x):
    path=STEMS/f'layer{i}.npy'; np.save(path,x.astype(np.float32)); print('saved',path,'peak',float(np.max(np.abs(x))))

def layer1():
    core=np.full(N,.0016,np.float32); h2=np.full(N,.00045,np.float32); h4=np.full(N,.00030,np.float32); h8=np.full(N,.00018,np.float32)
    beat=0; pos=.14; focus='440'; strength=.75
    while pos<RAW_DUR:
        beat+=1; k=(beat-1)%5; fifth=k==4
        dur=1.32+(rng.random()-.5)*.16
        local=[.52,.70,.88,.58,.72][k]; peak=local*strength*(.86+rng.random()*.27)
        a=int(pos*SR); b=min(N,int((pos+dur)*SR)); m=b-a
        if m>1:
            x=np.linspace(0,1,m,endpoint=False); shape=np.power(np.maximum(0,np.sin(np.pi*x)),1.7)
            core[a:b]=.0016+(peak-.0016)*shape
            vals={'440':(.075,.014,.0055),'880':(.018,.070,.0065),'1760':(.010,.024,.060)}[focus]
            acc=1.72 if fifth else .74
            for arr,val,floor,powr in [(h2,vals[0]*acc,.00045,1.66),(h4,vals[1]*acc,.00030,1.62),(h8,vals[2]*acc,.00018,1.58)]:
                sh=np.power(np.maximum(0,np.sin(np.pi*x)),powr); arr[a:b]=floor+(val-floor)*sh
        if fifth:
            r=rng.random()
            if focus=='440': focus='880' if r<.58 else ('440' if r<.82 else '1760')
            elif focus=='880': focus='440' if r<.34 else ('880' if r<.72 else '1760')
            else: focus='880' if r<.55 else ('440' if r<.80 else '1760')
            strength=float(np.clip(strength+(rng.random()-.5)*.34,.52,1))
        pos+=dur
    y=np.zeros((N,2),np.float32)
    for f,a,p in [(220.46,.74,0),(223.39,.38,.045),(216.80,.24,-.045)]:y+=sine_voice(f,a*core,p)
    for f,a,p in [(433.59,.16,-.22),(437.26,.13,-.10),(440.92,.26,.08),(446.78,.34,.24)]:y+=sine_voice(f,a*h2,p)
    for f,a,p in [(872.31,.055,-.92),(879.64,.18,-.48),(882.57,.18,.46),(889.16,.050,.92)]:y+=sine_voice(f,a*h4,p)
    for f,a,p in [(1754.88,.040,-.94),(1759.28,.145,0),(1764.40,.038,.94)]:y+=sine_voice(f,a*h8,p)
    y=simple_space(y,.28,.82)*BASE[0]
    return y

def parse_layer2():
    s=LAYER_HTML[1]
    ev=json.loads(re.search(r'const EVENTS=(\[.*?\]);',s,re.S).group(1))
    hi=json.loads(re.search(r'const HIGH_EVENTS=(\[.*?\]);',s,re.S).group(1))
    intervals=json.loads(re.search(r'const INTERVALS=(\[.*?\]);',s,re.S).group(1))
    return ev,hi,intervals

def pan_for(f):
    if f>=1400:return .9 if int(f)%2 else -.9
    if f>=800:return .65 if int(f)%2 else -.65
    if f>=500:return -.35
    if f>=300:return .12
    return 0

def layer2():
    evs,his,ints=parse_layer2(); y=np.zeros((N,2),np.float32)
    # measured-ish/generative pulse sequence
    pos=.4; idx=0
    while pos<RAW_DUR:
        if pos<13: idx=min(len(evs)-1,int(pos/.55)%len(evs))
        else: idx=int(rng.integers(0,len(evs)))
        ev=evs[idx]; gap=float(rng.choice(ints))*.42*(.96+rng.random()*.08); dur=float(np.clip(gap*2.2,.55,1.55))
        strength=ev['s']*(.9+rng.random()*.18)
        for f,rel in ev['c']:
            amp=.088*strength*rel
            if f<210:amp*=.86
            if f>700:amp*=.78
            if f>1500:amp*=.92
            add_tone_segment(y,pos,dur,f,amp,pan_for(f),1.72,(rng.random()-.5)*1.2)
        for j,(f,rel) in enumerate(his[idx][:2]):
            amp=.095*strength*rel*(.92 if f>=1450 else 1)*(.82 if f>=1700 else 1)
            pan=(-1 if j%2==0 else 1)*(.96 if f>=1700 else (.88 if f>=1450 else .72))
            add_tone_segment(y,pos+.025,dur*1.12,f,amp,pan,2.05,(rng.random()-.5))
        pos+=max(.16,gap)
    # continuous moving 440 ribbon
    cents=11*np.sin(2*np.pi*.78*t)+4.8*np.sin(2*np.pi*3.35*t)+1.8*np.sin(2*np.pi*4.15*t)
    dev=440*np.log(2)/1200*cents
    phase=2*np.pi*440*t + 2*np.pi*np.cumsum(dev)/SR
    env=(.102+.026*np.sin(2*np.pi*.66*t)).astype(np.float32)
    sig=np.sin(phase).astype(np.float32)*(.145*.25)*env
    l,r=pan_gains(.06);y[:,0]+=sig*l;y[:,1]+=sig*r
    # base loop ribbon partials
    for k,(f,a,p,slow,dep) in enumerate([(220,.20,0,.70,7),(296,.10,-.08,.63,9),(445,.075,.10,.70,12),(882,.045,-.72,.73,8),(1175,.028,.66,.63,7),(1758,.022,-.92,.73,5.5)]):
        amp=(.085+.028*np.sin(2*np.pi*.17*t))*a*.34
        amp*=1+(.25 if f<500 else .34)*np.sin(2*np.pi*((.73 if k%2==0 else .63)+k*.011)*t)
        y+=sine_voice(f,amp,p,slow+k*.017,dep)
    y=simple_space(y,.22,.9)*BASE[1]
    return y

def layer3():
    body=.085+.060*np.sin(2*np.pi*.77*t)+.040*np.sin(2*np.pi*.12*t); body=np.maximum(.002,body)
    octe=.34+.034*np.sin(2*np.pi*.81*t); high=.30+.030*np.sin(2*np.pi*.74*t)
    y=np.zeros((N,2),np.float32)
    for f,a,p,d,c in [(288.68,.50,-.08,.071,1.4),(292.38,.66,-.03,.083,1.3),(294.74,.82,.02,.097,1.2),(297.76,.63,.07,.109,1.5)]:y+=sine_voice(f,a*body*.72,p,d,c)
    for f,a,p,d,c in [(583.42,.050,-.86,.09,1.2),(586.44,.085,-.44,.104,1),(587.45,.060,.45,.118,1.1),(590.14,.038,.88,.133,1.4)]:y+=sine_voice(f,a*octe*.060,p,d,c)
    for f,a,p,d,c in [(1172.21,.048,-.9,.079,.8),(1173.9,.072,-.34,.101,.9),(1174.57,.078,.32,.123,.8),(1179.95,.032,.92,.139,1)]:y+=sine_voice(f,a*high*.05,p,d,c)
    return simple_space(y,.10,.82)*BASE[2]

def paused_env(freq,floor,ran,slowf,slowd):
    x=np.sin(2*np.pi*freq*t); th=-.18; u=np.clip((x-th)/(1-th),0,1); sh=u*u*(3-2*u)
    return np.maximum(0,floor+ran*sh+slowd*np.sin(2*np.pi*slowf*t)).astype(np.float32)

def layer4():
    b=paused_env(.40,.006,.136,.060,.0035);h2=paused_env(.42,.0025,.050,.056,.0012);h4=paused_env(.38,.0015,.029,.064,.0008);h6=paused_env(.41,.00035,.0072,.052,.00022)
    y=np.zeros((N,2),np.float32)
    for f,a,p,d,c in [(319.34,.10,-.05,.061,1.1),(324.46,.62,-.025,.073,1.2),(329.96,.88,.015,.087,1),(334.35,.34,.05,.103,1.3)]:y+=sine_voice(f,a*b*.78,p,d,c)
    for f,a,p,d,c in [(655.88,.045,-.9,.078,1),(665.41,.095,-.45,.094,1),(667.24,.055,.46,.111,1.1),(669.07,.050,.91,.126,1)]:y+=sine_voice(f,a*h2*.20,p,d,c)
    for f,a,p,d,c in [(1312.13,.03,-.94,.069,.8),(1316.53,.038,-.34,.089,.9),(1329.35,.06,.36,.114,.8),(1374.76,.022,.94,.131,.9)]:y+=sine_voice(f,a*h4*.15,p,d,c)
    for f,a,p,d,c in [(1913.09,.012,-.88,.081,.55),(1936.52,.01,-.30,.097,.55),(1951.17,.011,.32,.113,.6),(1965.82,.018,.90,.129,.55)]:y+=sine_voice(f,a*h6*.085,p,d,c)
    return simple_space(y,.18,.9)*BASE[3]

def smooth_state_envelopes():
    keys=['g4','fs4','g5','fs5','g6']; env={k:np.full(N,.0001,np.float32) for k in keys}
    states=[('fs5',4.7,dict(g4=.020,fs4=.006,g5=.006,fs5=.090,g6=.008)),('quiet',3.7,dict(g4=.030,fs4=.006,g5=.006,fs5=.020,g6=.015)),('g6',5.2,dict(g4=.040,fs4=.006,g5=.012,fs5=.004,g6=.100)),('body',4.0,dict(g4=.150,fs4=.012,g5=.060,fs5=.003,g6=.030)),('g5',3.6,dict(g4=.080,fs4=.040,g5=.130,fs5=.002,g6=.010)),('fs4',3.3,dict(g4=.050,fs4=.125,g5=.045,fs5=.002,g6=.006)),('body2',5.0,dict(g4=.180,fs4=.018,g5=.085,fs5=.002,g6=.010))]
    gen=[dict(g4=.022,fs4=.006,g5=.008,fs5=.075,g6=.008),dict(g4=.035,fs4=.006,g5=.015,fs5=.003,g6=.088),dict(g4=.145,fs4=.014,g5=.060,fs5=.002,g6=.018),dict(g4=.075,fs4=.032,g5=.115,fs5=.002,g6=.010),dict(g4=.050,fs4=.105,g5=.042,fs5=.002,g6=.006),dict(g4=.170,fs4=.018,g5=.080,fs5=.002,g6=.010)]
    pos=0; seq=[]
    for _,d,st in states: seq.append((d,st))
    prev=-1
    while sum(d for d,_ in seq)<RAW_DUR+2:
        choices=[i for i in range(len(gen)) if i!=prev]; i=int(rng.choice(choices)); prev=i; seq.append((3+rng.random()*3.1,gen[i]))
    cur={k:.0001 for k in keys}; idx0=0
    for dur,st in seq:
        a=idx0;b=min(N,int((idx0/SR+dur)*SR));m=b-a
        if m<=0:break
        ramp=min(m,int((.85+rng.random()*.65)*SR));
        for k in keys:
            arr=env[k]; target=st[k]
            if ramp>1: arr[a:a+ramp]=np.linspace(cur[k],target,ramp,endpoint=False,dtype=np.float32)
            arr[a+ramp:b]=target; cur[k]=target
        idx0=b
    return env

def layer5():
    env=smooth_state_envelopes(); y=np.zeros((N,2),np.float32)
    groups={
     'g4':([(387.08,.11,-.08,.061,1),(391.11,.70,-.025,.073,1.1),(392.58,.36,.015,.087,1),(394.04,.24,.045,.101,1.2),(397.71,.10,.08,.119,1.1)],.50),
     'fs4':([(368.04,.12,-.08,.067,1),(370.97,.56,0,.081,1.1),(375.73,.26,.08,.103,1)],.33),
     'g5':([(776.37,.12,-.82,.071,.9),(784.06,.22,-.42,.089,.9),(786.62,.54,.44,.107,1),(788.45,.13,.84,.129,.9)],.16),
     'fs5':([(740,.18,-.68,.076,.9),(744.14,.50,.66,.099,1)],.12),
     'g6':([(1565.92,.42,-.88,.069,.65),(1569.21,.20,-.28,.091,.7),(1571.41,.28,.34,.113,.65),(1575.07,.09,.90,.137,.7)],.09)}
    for k,(voices,outg) in groups.items():
        e=env[k]
        # mild breath motion matching layer
        bf={'g4':.72,'fs4':.68,'g5':.65,'fs5':.58,'g6':.73}[k]
        e=e*(1+.10*np.sin(2*np.pi*bf*t))
        for f,a,p,d,c in voices:y+=sine_voice(f,a*e*outg,p,d,c)
    return simple_space(y,.13,.72)*BASE[4]

def layer6():
    s=LAYER_HTML[5]; specs=json.loads(re.search(r'const SPECS=(\[.*?\]);',s,re.S).group(1)); cd=float(re.search(r'const CURVE_DURATION=([0-9.]+);',s).group(1))
    y=np.zeros((N,2),np.float32); pos=.06
    while pos<RAW_DUR:
        scale=.92+rng.random()*.18 if pos>cd else 1.0; level=.88+rng.random()*.20 if pos>cd else 1.0
        m=int(cd*scale*SR); a=int(pos*SR); b=min(N,a+m); xx=np.linspace(0,1,b-a,endpoint=False)
        for sp in specs:
            curve=np.asarray(sp['curve'],dtype=np.float32); xi=np.linspace(0,1,len(curve)); env=np.interp(xx,xi,curve).astype(np.float32)*sp['scale']*level
            tt=np.arange(b-a,dtype=np.float64)/SR; cents=(rng.random()-.5)*.9; f=sp['f']*2**(cents/1200); sig=np.sin(2*np.pi*f*tt+rng.uniform(0,2*np.pi)).astype(np.float32)*env
            l,r=pan_gains(sp['pan']); y[a:b,0]+=sig*l; y[a:b,1]+=sig*r
        pos+=cd*scale
    return simple_space(y,.08,.95)*BASE[5]

layers=[layer1,layer2,layer3,layer4,layer5,layer6]
for i,fn in enumerate(layers,1):
    p=STEMS/f'layer{i}.npy'
    if not p.exists(): save_stem(i,fn())

weights={
 'morning':[.95,1.16,.92,.88,.95,1.12],
 'afternoon':[1,1,1,1,1,1],
 'evening':[.78,.42,.68,.68,1.42,.36],
 'offhours':[.55,.20,.56,1.08,1.12,.18],
}
# common scale based on afternoon peak, preserving quieter night
aft=sum(np.load(STEMS/f'layer{i}.npy',mmap_mode='r')*weights['afternoon'][i-1] for i in range(1,7))
peak=float(np.max(np.abs(aft))); global_scale=.72/max(peak,1e-6); del aft
print('global scale',global_scale)
for name,w in weights.items():
    mix=np.zeros((N,2),np.float32)
    for i,ww in enumerate(w,1): mix += np.load(STEMS/f'layer{i}.npy',mmap_mode='r')*ww
    mix*=global_scale
    mix=np.tanh(mix*1.05).astype(np.float32)/np.tanh(1.05)
    out=circularize(mix)
    wav=OUT/f'homepod-{name}.wav'
    m4a=OUT/f'homepod-{name}.m4a'
    reverse_m4a=OUT/f'homepod-{name}-reverse.m4a'
    wavfile.write(wav,SR,(np.clip(out,-1,1)*32767).astype(np.int16))
    subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(wav),'-c:a','aac','-b:a','48k','-ar','44100',str(m4a)],check=True)
    subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-i',str(wav),'-af','areverse','-c:a','aac','-b:a','48k','-ar','44100',str(reverse_m4a)],check=True)
    wav.unlink()
    print(name,m4a.stat().st_size,'bytes',reverse_m4a.stat().st_size,'reverse bytes','peak',float(np.max(np.abs(out))), 'rms',float(np.sqrt(np.mean(out**2))))
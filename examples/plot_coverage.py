"""Optional Matplotlib plots from saved audit JSON; no solver imports needed."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('audit',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR',str(args.output.resolve()/'.matplotlib-cache'))
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError as exc:raise SystemExit('Run this optional script with an interpreter that has Matplotlib installed.') from exc
    data=json.loads(args.audit.read_text());args.output.mkdir(parents=True,exist_ok=True)
    windows=data['windows'];times=[w['time_seconds'] for w in windows]
    fig,axes=plt.subplots(3,1,figsize=(11,9),sharex=True,layout='constrained')
    axes[0].plot(times,[w['covered_users'] for w in windows],'o-',label='Users with visible access')
    axes[0].plot(times,[w['preflight']['access']['flow'] for w in windows],'s--',label='Access matching flow')
    axes[0].plot(times,[w['preflight']['egress']['flow'] for w in windows],'^:',label='Egress matching flow')
    axes[0].axhline(data['user_count'],color='black',linestyle='--',label='Required users')
    axes[0].set_ylabel('Users / flow units');axes[0].legend(fontsize=9)
    axes[1].plot(times,[w['region_union_visible_satellites'] for w in windows],'o-',label='Satellites seen by population')
    if data['region_bound']:axes[1].axhline(data['region_bound']['maximum_region_visible_satellites'],color='red',linestyle='--',label='Independent frozen-region upper bound')
    axes[1].set_ylabel('Satellite count');axes[1].legend(fontsize=9)
    axes[2].plot(times,[w['isl_edges'] for w in windows],'o-',label='Retained undirected ISLs')
    axes[2].plot(times,[len(w['components']) for w in windows],'s--',label='Connected components')
    axes[2].set_ylabel('Graph count');axes[2].set_xlabel('Snapshot time since synthetic epoch (seconds)');axes[2].legend(fontsize=9)
    for ax in axes:ax.grid(alpha=.2)
    fig.suptitle(data['family_id']+' — coverage and necessary-condition audit\nNo users/edges added to repair coverage; snapshots do not imply continuous links')
    fig.savefig(args.output/'coverage.png',dpi=160);plt.close(fig)
    if 'snapshot0_positions_ecef_m' in data:
        coords={n:(math.degrees(math.atan2(v[1],v[0])),math.degrees(math.atan2(v[2],math.hypot(v[0],v[1])))) for n,v in data['snapshot0_positions_ecef_m'].items()}
        fig,ax=plt.subplots(figsize=(11,6),layout='constrained')
        for a,b in data['snapshot0_edges']:
            if abs(coords[a][0]-coords[b][0])<=180:ax.plot([coords[a][0],coords[b][0]],[coords[a][1],coords[b][1]],color='#9aafc0',linewidth=.7,zorder=1)
        ax.scatter([v[0] for v in coords.values()],[v[1] for v in coords.values()],s=18,label='Satellite subpoints',zorder=2)
        ax.scatter([v['longitude'] for v in data['layout']],[v['latitude'] for v in data['layout']],marker='x',color='red',s=30,label='Users',zorder=3)
        ax.scatter([v['longitude'] for v in data['ground_stations']],[v['latitude'] for v in data['ground_stations']],marker='^',color='green',s=55,label='Ground stations',zorder=4)
        ax.set(xlim=(-180,180),ylim=(-90,90),xlabel='ECEF longitude (degrees)',ylabel='Geocentric latitude (degrees)',
               title=data['family_id']+' — snapshot0 connectivity\nDateline-crossing lines omitted from drawing only; full edge set retained in audit')
        ax.grid(alpha=.2);ax.legend(loc='lower left');fig.savefig(args.output/'connectivity.png',dpi=160);plt.close(fig)
    (args.output/'plot_provenance.json').write_text(json.dumps({'audit_sha256':hashlib.sha256(args.audit.read_bytes()).hexdigest(),
        'plot_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'python':sys.version,'matplotlib':matplotlib.__version__,'scope':'plots of saved audit data; not optimizer outputs'},indent=2))


if __name__=='__main__':main()

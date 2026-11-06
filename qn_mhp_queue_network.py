"""
QN-MHP-style discrete-event steering simulation, based on Section 2.2.2 and Appendix A.

Paper-derived structure:
  paired near/far visual entities every 50 ms
  Server 1 -> Server 2/3 -> Server 4 -> Server A -> Server C -> Server W -> Server Y -> Server Z
  A stores visual angles; C computes steering adjustment; Z completion updates vehicle dynamics.

CAUTION:
The paper section does not provide all numerical service times and calibrated control gains.
The values in CONFIG are editable provisional values, not claimed to be the original MATLAB
parameter set. This is a transparent reconstruction, not an exact reproduction.
"""
from collections import deque
from dataclasses import dataclass
import numpy as np

CONFIG = {
    "dt": 0.01, "visual_interval": 0.05, "duration": 8.0,
    "speed": 29.0, "wheelbase": 2.7, "near_distance": 10.0, "far_thw": 4.0,
    # provisional server service times (seconds), replace with verified source values
    "service": {"1": .042, "2/3": .042, "4": .042, "A": .018,
                "C": .050, "W": .024, "Y": .024, "Z": .024},
    # provisional Salvucci-style control gains, not verified original values
    "k_far": -.8, "k_near": -.8, "k_i": -.5, "theta_nmax_deg": 20,
    "max_phi_deg": 45, "initial_offsets": [.3, .6, .9, 1.2],
}
ROUTE = ["1", "2/3", "4", "A", "C", "W", "Y", "Z"]

@dataclass
class Entity:
    kind: str
    value: float
    sample_time: float
    pair: tuple = None

class Server:
    def __init__(self, name, service):
        self.name, self.service = name, service
        self.queue = deque()
        self.entity = None
        self.remaining = 0.0
    def push(self, entity):
        self.queue.append(entity)
    def advance(self, dt):
        if self.entity is None and self.queue:
            self.entity = self.queue.popleft()
            self.remaining = self.service
        if self.entity is None:
            return None
        self.remaining -= dt
        if self.remaining <= 1e-12:
            e, self.entity = self.entity, None
            self.remaining = 0.0
            return e
        return None

def simulate(x0):
    c = CONFIG; dt = c["dt"]
    time = np.arange(0, c["duration"] + dt/2, dt); n = len(time)
    x=np.zeros(n); z=np.zeros(n); yaw=np.zeros(n); phi=np.zeros(n)
    tn=np.zeros(n); tf=np.zeros(n); x[0]=x0
    def angles(i):
        tn[i]=np.arctan(x[i]/c["near_distance"])+yaw[i]
        tf[i]=np.arctan(x[i]/(c["far_thw"]*c["speed"]))+yaw[i]
    angles(0)
    servers={s:Server(s,c["service"][s]) for s in ROUTE}
    route_i={s:i for i,s in enumerate(ROUTE)}
    tick=max(1,round(c["visual_interval"]/dt))
    latest={"near":None,"far":None}
    fresh={"near":False,"far":False}
    prev_control=None
    pending_actions=deque()

    for i in range(1,n):
        t=time[i]
        # vehicle dynamics using the currently applied steering angle
        ds=c["speed"]*dt
        R=1e6 if abs(phi[i-1])<1e-9 else c["wheelbase"]/np.sin(phi[i-1])
        alpha=ds/R
        x[i]=x[i-1]+2*abs(R)*np.sin(alpha/2)*np.sin(yaw[i-1]+alpha/2)
        z[i]=z[i-1]+2*abs(R)*np.sin(alpha/2)*np.cos(yaw[i-1]+alpha/2)
        yaw[i]=yaw[i-1]+alpha
        phi[i]=phi[i-1]
        angles(i)

        # apply completed motor actions at the hand/vehicle interface
        while pending_actions and pending_actions[0][0] <= t+1e-12:
            _, adjustment = pending_actions.popleft()
            phi[i]=np.clip(phi[i]+adjustment,
                           -np.deg2rad(c["max_phi_deg"]), np.deg2rad(c["max_phi_deg"]))

        # visual stimuli are generated as two streams every 50 ms
        if i % tick == 0:
            servers["1"].push(Entity("near",tn[i],t))
            servers["1"].push(Entity("far",tf[i],t))

        # process downstream first; one server completion per server per tick
        for s in reversed(ROUTE):
            e=servers[s].advance(dt)
            if e is None: continue
            if s=="Z":
                pending_actions.append((t,e.value))
            elif s=="A":
                latest[e.kind]=e
                fresh[e.kind]=True
                if fresh["near"] and fresh["far"]:
                    near_e,far_e=latest["near"],latest["far"]
                    pair=(near_e.value,far_e.value,max(near_e.sample_time,far_e.sample_time))
                    servers["C"].push(Entity("control",0.0,pair[2],pair))
                    fresh["near"]=fresh["far"]=False
            elif s=="C":
                near_now,far_now,sample_t=e.pair
                if prev_control is None:
                    dn=df=0.0
                    elapsed=c["visual_interval"]
                else:
                    pn,pf,pt=prev_control
                    dn=near_now-pn; df=far_now-pf
                    elapsed=max(c["visual_interval"],sample_t-pt)
                cap=np.deg2rad(c["theta_nmax_deg"])
                limited=np.clip(near_now,-cap,cap)
                adjustment=(c["k_far"]*df+c["k_near"]*dn+c["k_i"]*limited*elapsed)
                prev_control=(near_now,far_now,sample_t)
                e.value=adjustment
                servers["W"].push(e)
            else:
                next_s=ROUTE[route_i[s]+1]
                servers[next_s].push(e)

        # do not overwrite a newly applied steering action
        if not pending_actions and (i == 1 or phi[i] == phi[i-1]):
            pass

    return {"time":time,"x":x,"z":z,"yaw":yaw,"phi":phi,"theta_near":tn,"theta_far":tf}

def main():
    for o in CONFIG["initial_offsets"]:
        r = simulate(o)
        print(
            f"initial offset={o:.1f} m; final x={r['x'][-1]:.4f} m; "
            f"final yaw={np.rad2deg(r['yaw'][-1]):.3f} deg"
        )
    print("NOTE: Service times and controller gains are provisional; see CONFIG.")

if __name__=="__main__":
    main()

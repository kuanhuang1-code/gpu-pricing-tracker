import json, random, sys, re
from datetime import datetime, timedelta
from pathlib import Path

DATA_FILE = Path(__file__).parent / "gpu_pricing_data.json"
# (start_price, current_price, volatility, min_floor)
GPUS = {
    "GB300":(12.00,10.00,0.50,7.00),
    "GB200":(8.00,6.50,0.40,4.50),
    "B300":(6.00,5.00,0.30,3.50),
    "B200":(5.00,3.99,0.20,2.50),
    "H200 SXM":(5.50,4.30,0.15,2.80),
    "H100 SXM":(4.80,2.99,0.12,1.80),
    "A100 80GB":(2.30,1.29,0.08,0.80),
    "A100 40GB":(1.80,0.95,0.06,0.55),
    "L40S":(1.90,1.20,0.07,0.70),
    "L40":(1.50,0.67,0.05,0.40),
    "RTX 6000 Ada":(1.20,0.70,0.05,0.40),
    "RTX 5090":(0.80,0.45,0.04,0.25),
    "RTX 4090":(0.69,0.44,0.04,0.20),
    "RTX 3090":(0.30,0.15,0.02,0.08),
    "L4":(0.65,0.39,0.03,0.18),
    "A40":(0.60,0.35,0.03,0.15),
    "T4":(0.45,0.29,0.02,0.10),
    "V100":(0.40,0.22,0.02,0.08),
    "AMD MI300X":(3.50,1.99,0.15,1.20),
    "AMD MI325X":(4.00,2.29,0.15,1.50),
}

def load():
    if DATA_FILE.exists():
        with open(DATA_FILE) as f: return json.load(f)
    return {"metadata":{"tracked_gpus":list(GPUS.keys())},"entries":[]}

def save(data):
    with open(DATA_FILE,"w") as f: json.dump(data, f, indent=2)

def init():
    random.seed(42)
    base = datetime.now() - timedelta(weeks=20)
    entries = []
    for w in range(20):
        d = base + timedelta(weeks=w)
        p = w / 19
        prices = {}
        for gpu,(s,e,v,f) in GPUS.items():
            prices[gpu] = round(max(f, s + (e-s)*p + random.uniform(-v,v)), 2)
        entries.append({"date":d.strftime("%Y-%m-%d"),"week":f"W{d.isocalendar()[1]:02d}","prices":prices})
    data = {"metadata":{"tracked_gpus":list(GPUS.keys())},"entries":entries}
    save(data)
    print(f"Created {len(entries)} weekly entries with {len(GPUS)} GPUs")

def scrape_prices():
    import requests
    prices = {}
    headers = {"User-Agent":"Mozilla/5.0 GPUTracker/1.0"}

    try:
        print("Scraping getdeploying.com...")
        r = requests.get("https://getdeploying.com/reference/cloud-gpu", headers=headers, timeout=15)
        if r.ok:
            t = r.text
            for gpu in GPUS:
                idx = t.find(gpu)
                if idx >= 0:
                    m = re.search(r'From\s*\$(\d+\.?\d*)/h', t[idx:idx+300])
                    if m:
                        p = float(m.group(1))
                        floor = GPUS[gpu][3]
                        if p >= floor:
                            prices[gpu] = p
                            print(f"  {gpu}: ${p:.2f}/hr [getdeploying]")
                        else:
                            print(f"  {gpu}: ${p:.2f}/hr [getdeploying] REJECTED (below ${floor:.2f} floor)")
    except Exception as e:
        print(f"  getdeploying failed: {e}")

    try:
        print("Scraping RunPod...")
        r = requests.get("https://api.runpod.io/graphql?query={gpuTypes{id%20displayName%20lowestPrice{minimumBidPrice%20minPricePerHr}}}", headers=headers, timeout=15)
        if r.ok:
            data = r.json()
            gpu_map = {"H100 SXM":"H100 SXM","H200 SXM":"H200","A100 80GB":"A100 80GB","A100 40GB":"A100","RTX 4090":"RTX 4090","RTX 3090":"RTX 3090","L40S":"L40S","L40":"L40","L4":"L4","T4":"T4","RTX 5090":"RTX 5090","RTX 6000 Ada":"RTX 6000","A40":"A40","AMD MI300X":"MI300X"}
            for item in data.get("data",{}).get("gpuTypes",[]):
                name = item.get("displayName","")
                for our_name, rp_match in gpu_map.items():
                    if rp_match.lower() in name.lower():
                        lp = item.get("lowestPrice",{})
                        if lp:
                            p = float(lp.get("minPricePerHr",0) or lp.get("minimumBidPrice",0) or 0)
                            floor = GPUS[our_name][3]
                            if p >= floor and (our_name not in prices or p < prices[our_name]):
                                prices[our_name] = round(p, 2)
                                print(f"  {our_name}: ${p:.2f}/hr [runpod]")
    except Exception as e:
        print(f"  RunPod failed: {e}")

    try:
        print("Scraping vast.ai...")
        r = requests.get("https://cloud.vast.ai/api/v0/bundles/?q={%22type%22:%22on-demand%22,%22verified%22:{%22eq%22:true}}", headers=headers, timeout=15)
        if r.ok:
            offers = r.json().get("offers",[])
            gpu_map = {"H100 SXM":"H100","H200 SXM":"H200","A100 80GB":"A100_SXM","RTX 4090":"RTX_4090","RTX 3090":"RTX_3090","L40S":"L40S","L4":"L4","T4":"T4","A40":"A40","RTX 5090":"RTX_5090","AMD MI300X":"MI300X"}
            for our_name, vast_name in gpu_map.items():
                matching = [o for o in offers if vast_name.lower() in o.get("gpu_name","").lower()]
                if matching:
                    cheapest = min(matching, key=lambda x: x.get("dph_total",999))
                    p = round(cheapest.get("dph_total",0), 2)
                    floor = GPUS[our_name][3]
                    if p >= floor and (our_name not in prices or p < prices[our_name]):
                        prices[our_name] = p
                        print(f"  {our_name}: ${p:.2f}/hr [vast.ai]")
                    elif p > 0:
                        print(f"  {our_name}: ${p:.2f}/hr [vast.ai] REJECTED (below ${floor:.2f} floor)")
    except Exception as e:
        print(f"  vast.ai failed: {e}")

    return prices

def collect():
    data = load()
    if not data["entries"]:
        print("No data. Run with --init first.")
        return
    last = data["entries"][-1]
    today = datetime.now()

    scraped = {}
    try:
        scraped = scrape_prices()
        print(f"\nScraped {len(scraped)} GPU prices from the web.")
    except Exception as e:
        print(f"Scraping failed: {e}")

    prices = {}
    for gpu in GPUS:
        if gpu in scraped:
            prices[gpu] = scraped[gpu]
        else:
            prev = last["prices"].get(gpu, GPUS[gpu][1])
            change = random.uniform(-0.05, 0.03)
            prices[gpu] = round(max(GPUS[gpu][3], prev + change), 2)
            print(f"  {gpu}: ${prices[gpu]:.2f}/hr (estimated)")

    entry = {"date":today.strftime("%Y-%m-%d"),"week":f"W{today.isocalendar()[1]:02d}","prices":prices}
    data["entries"].append(entry)
    save(data)
    print(f"\nAdded week {entry['week']}. Total: {len(data['entries'])} entries.")
    print("\nFinal prices:")
    for gpu, p in sorted(prices.items(), key=lambda x: -x[1]):
        src = "LIVE" if gpu in scraped else "est"
        print(f"  {gpu}: ${p:.2f}/hr ({src})")

if __name__=="__main__":
    if "--init" in sys.argv: init()
    else: collect()
ENDOFFILEcat > gpu_price_collector.py << 'ENDOFFILE'
import json, random, sys, re
from datetime import datetime, timedelta
from pathlib import Path

DATA_FILE = Path(__file__).parent / "gpu_pricing_data.json"
# (start_price, current_price, volatility, min_floor)
GPUS = {
    "GB300":(12.00,10.00,0.50,7.00),
    "GB200":(8.00,6.50,0.40,4.50),
    "B300":(6.00,5.00,0.30,3.50),
    "B200":(5.00,3.99,0.20,2.50),
    "H200 SXM":(5.50,4.30,0.15,2.80),
    "H100 SXM":(4.80,2.99,0.12,1.80),
    "A100 80GB":(2.30,1.29,0.08,0.80),
    "A100 40GB":(1.80,0.95,0.06,0.55),
    "L40S":(1.90,1.20,0.07,0.70),
    "L40":(1.50,0.67,0.05,0.40),
    "RTX 6000 Ada":(1.20,0.70,0.05,0.40),
    "RTX 5090":(0.80,0.45,0.04,0.25),
    "RTX 4090":(0.69,0.44,0.04,0.20),
    "RTX 3090":(0.30,0.15,0.02,0.08),
    "L4":(0.65,0.39,0.03,0.18),
    "A40":(0.60,0.35,0.03,0.15),
    "T4":(0.45,0.29,0.02,0.10),
    "V100":(0.40,0.22,0.02,0.08),
    "AMD MI300X":(3.50,1.99,0.15,1.20),
    "AMD MI325X":(4.00,2.29,0.15,1.50),
}

def load():
    if DATA_FILE.exists():
        with open(DATA_FILE) as f: return json.load(f)
    return {"metadata":{"tracked_gpus":list(GPUS.keys())},"entries":[]}

def save(data):
    with open(DATA_FILE,"w") as f: json.dump(data, f, indent=2)

def init():
    random.seed(42)
    base = datetime.now() - timedelta(weeks=20)
    entries = []
    for w in range(20):
        d = base + timedelta(weeks=w)
        p = w / 19
        prices = {}
        for gpu,(s,e,v,f) in GPUS.items():
            prices[gpu] = round(max(f, s + (e-s)*p + random.uniform(-v,v)), 2)
        entries.append({"date":d.strftime("%Y-%m-%d"),"week":f"W{d.isocalendar()[1]:02d}","prices":prices})
    data = {"metadata":{"tracked_gpus":list(GPUS.keys())},"entries":entries}
    save(data)
    print(f"Created {len(entries)} weekly entries with {len(GPUS)} GPUs")

def scrape_prices():
    import requests
    prices = {}
    headers = {"User-Agent":"Mozilla/5.0 GPUTracker/1.0"}

    try:
        print("Scraping getdeploying.com...")
        r = requests.get("https://getdeploying.com/reference/cloud-gpu", headers=headers, timeout=15)
        if r.ok:
            t = r.text
            for gpu in GPUS:
                idx = t.find(gpu)
                if idx >= 0:
                    m = re.search(r'From\s*\$(\d+\.?\d*)/h', t[idx:idx+300])
                    if m:
                        p = float(m.group(1))
                        floor = GPUS[gpu][3]
                        if p >= floor:
                            prices[gpu] = p
                            print(f"  {gpu}: ${p:.2f}/hr [getdeploying]")
                        else:
                            print(f"  {gpu}: ${p:.2f}/hr [getdeploying] REJECTED (below ${floor:.2f} floor)")
    except Exception as e:
        print(f"  getdeploying failed: {e}")

    try:
        print("Scraping RunPod...")
        r = requests.get("https://api.runpod.io/graphql?query={gpuTypes{id%20displayName%20lowestPrice{minimumBidPrice%20minPricePerHr}}}", headers=headers, timeout=15)
        if r.ok:
            data = r.json()
            gpu_map = {"H100 SXM":"H100 SXM","H200 SXM":"H200","A100 80GB":"A100 80GB","A100 40GB":"A100","RTX 4090":"RTX 4090","RTX 3090":"RTX 3090","L40S":"L40S","L40":"L40","L4":"L4","T4":"T4","RTX 5090":"RTX 5090","RTX 6000 Ada":"RTX 6000","A40":"A40","AMD MI300X":"MI300X"}
            for item in data.get("data",{}).get("gpuTypes",[]):
                name = item.get("displayName","")
                for our_name, rp_match in gpu_map.items():
                    if rp_match.lower() in name.lower():
                        lp = item.get("lowestPrice",{})
                        if lp:
                            p = float(lp.get("minPricePerHr",0) or lp.get("minimumBidPrice",0) or 0)
                            floor = GPUS[our_name][3]
                            if p >= floor and (our_name not in prices or p < prices[our_name]):
                                prices[our_name] = round(p, 2)
                                print(f"  {our_name}: ${p:.2f}/hr [runpod]")
    except Exception as e:
        print(f"  RunPod failed: {e}")

    try:
        print("Scraping vast.ai...")
        r = requests.get("https://cloud.vast.ai/api/v0/bundles/?q={%22type%22:%22on-demand%22,%22verified%22:{%22eq%22:true}}", headers=headers, timeout=15)
        if r.ok:
            offers = r.json().get("offers",[])
            gpu_map = {"H100 SXM":"H100","H200 SXM":"H200","A100 80GB":"A100_SXM","RTX 4090":"RTX_4090","RTX 3090":"RTX_3090","L40S":"L40S","L4":"L4","T4":"T4","A40":"A40","RTX 5090":"RTX_5090","AMD MI300X":"MI300X"}
            for our_name, vast_name in gpu_map.items():
                matching = [o for o in offers if vast_name.lower() in o.get("gpu_name","").lower()]
                if matching:
                    cheapest = min(matching, key=lambda x: x.get("dph_total",999))
                    p = round(cheapest.get("dph_total",0), 2)
                    floor = GPUS[our_name][3]
                    if p >= floor and (our_name not in prices or p < prices[our_name]):
                        prices[our_name] = p
                        print(f"  {our_name}: ${p:.2f}/hr [vast.ai]")
                    elif p > 0:
                        print(f"  {our_name}: ${p:.2f}/hr [vast.ai] REJECTED (below ${floor:.2f} floor)")
    except Exception as e:
        print(f"  vast.ai failed: {e}")

    return prices

def collect():
    data = load()
    if not data["entries"]:
        print("No data. Run with --init first.")
        return
    last = data["entries"][-1]
    today = datetime.now()

    scraped = {}
    try:
        scraped = scrape_prices()
        print(f"\nScraped {len(scraped)} GPU prices from the web.")
    except Exception as e:
        print(f"Scraping failed: {e}")

    prices = {}
    for gpu in GPUS:
        if gpu in scraped:
            prices[gpu] = scraped[gpu]
        else:
            prev = last["prices"].get(gpu, GPUS[gpu][1])
            change = random.uniform(-0.05, 0.03)
            prices[gpu] = round(max(GPUS[gpu][3], prev + change), 2)
            print(f"  {gpu}: ${prices[gpu]:.2f}/hr (estimated)")

    entry = {"date":today.strftime("%Y-%m-%d"),"week":f"W{today.isocalendar()[1]:02d}","prices":prices}
    data["entries"].append(entry)
    save(data)
    print(f"\nAdded week {entry['week']}. Total: {len(data['entries'])} entries.")
    print("\nFinal prices:")
    for gpu, p in sorted(prices.items(), key=lambda x: -x[1]):
        src = "LIVE" if gpu in scraped else "est"
        print(f"  {gpu}: ${p:.2f}/hr ({src})")

if __name__=="__main__":
    if "--init" in sys.argv: init()
    else: collect()

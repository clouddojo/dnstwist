# run in docker
time docker build -t dnstwist . && time docker run dnstwist -gmab -f csv short.com

# g = geoip
# m = mx record
# a = all
# b = site banner
# run in local env
./dnstwist.py -r short.com
./dnstwist.py -mab short.com
./dnstwist.py -mab -f json short.com | tee results.json | jq '.'
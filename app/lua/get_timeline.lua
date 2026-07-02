-- get_timeline.lua
-- KEYS[1]=timeline_key  ARGV[1]=now_timestamp  ARGV[2]=window_seconds
local timeline_key = KEYS[1]
local ts = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cutoff = ts - window
return redis.call("ZRANGEBYSCORE", timeline_key, cutoff, "+inf")
-- record_event.lua
-- KEYS[1]=timeline  KEYS[2]=model_hash  KEYS[3]=cache_hash  KEYS[4]=known_models_set
-- ARGV[1]=event_json ARGV[2]=timestamp ARGV[3]=model_name
-- ARGV[4]=cost ARGV[5]=tokens_used ARGV[6]=window_seconds ARGV[7]=cache_hit("1"/"0")

local timeline_key = KEYS[1]
local model_hash_key = KEYS[2]
local cache_hash_key = KEYS[3]
local known_models_set = KEYS[4]

local event_json = ARGV[1]
local ts = tonumber(ARGV[2])
local model_name = ARGV[3]
local cost = tonumber(ARGV[4])
local tokens = tonumber(ARGV[5])
local window = tonumber(ARGV[6])
local cache_hit = ARGV[7]

redis.call("ZADD", timeline_key, ts, event_json)
redis.call("SADD", known_models_set, model_name)

redis.call("HINCRBYFLOAT", model_hash_key, "cost", cost)
redis.call("HINCRBY", model_hash_key, "tokens", tokens)
redis.call("HINCRBY", model_hash_key, "count", 1)

if cache_hit == "1" then
    redis.call("HINCRBY", cache_hash_key, "hits", 1)
    redis.call("HINCRBY", cache_hash_key, "tokens_saved", tokens)
else
    redis.call("HINCRBY", cache_hash_key, "misses", 1)
    redis.call("HINCRBY", cache_hash_key, "tokens_processed", tokens)
end

local cutoff = ts - window
redis.call("ZREMRANGEBYSCORE", timeline_key, "-inf", cutoff)

return redis.status_reply("OK")
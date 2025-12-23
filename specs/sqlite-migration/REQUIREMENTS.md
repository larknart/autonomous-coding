# SQLite + FastAPI Migration Requirements

## Problem Statement

The autonomous coding system stores features (test cases) in a `feature_list.json` file. As projects grow, this file can contain 340+ features, causing several issues:

### Current Pain Points

1. **Context Window Overflow**: The JSON file can exceed the agent's context window when read fully
2. **Limited Visibility**: The coding agent uses `cat feature_list.json | head -50` to read features, meaning it can only see approximately 5 features out of 340
3. **Inefficient Operations**: Every update requires reading/writing the entire file
4. **Wasteful Token Usage**: Agents consume tokens reading data that isn't immediately relevant
5. **No Structured Queries**: Cannot efficiently query for "next pending feature" or "count of passing features"

### Example of Current Limitations

```bash
# Agent can only see first 50 lines (~5 features)
cat feature_list.json | head -50

# Counting requires full file scan
cat feature_list.json | grep '"passes": false' | wc -l
```

## Requirements

### Functional Requirements

1. **Feature Storage**
   - Store features in a SQLite database per project (`<project_dir>/features.db`)
   - Support all existing feature fields: id, priority, category, name, description, steps, passes
   - Auto-assign IDs and priorities based on insertion order

2. **API Endpoints**
   - `GET /features` - List features with pagination (limit, offset) and filtering (passes, category)
   - `GET /features/next` - Get the highest-priority pending feature
   - `GET /features/stats` - Get passing/total counts and percentage
   - `GET /features/{id}` - Get a specific feature
   - `POST /features/bulk` - Create multiple features in one request
   - `PATCH /features/{id}` - Update feature status (only `passes` field)
   - `GET /health` - Health check

3. **Server Lifecycle**
   - Server must start automatically when running `autonomous_agent_demo.py`
   - Server must stop gracefully when agent session ends
   - Server runs on `http://localhost:8765`

4. **Migration**
   - Auto-detect existing `feature_list.json` files
   - Import all features into SQLite database
   - Rename original JSON to `feature_list.json.backup.<timestamp>`
   - Skip migration if database already has data

### Non-Functional Requirements

1. **Token Efficiency**
   - Reduce token usage by ~90% per feature operation
   - Agent retrieves only what's needed (single feature, limited list)

2. **Scalability**
   - Support 50 to 5000+ features without performance degradation
   - Pagination prevents large response payloads

3. **Reliability**
   - Atomic database operations (no partial writes)
   - No file corruption risk from concurrent access

4. **Backward Compatibility**
   - Existing projects with `feature_list.json` are auto-migrated
   - Agent prompts use familiar curl/jq patterns

## Success Metrics

| Metric | Before | After |
|--------|--------|-------|
| Tokens per "view features" | ~500-1000 | ~50-100 |
| Features visible to agent | ~5 (head -50) | All (via pagination) |
| Update operation | Read-modify-write full file | Single PATCH request |
| Query capability | grep/sed | SQL-like filters |

## Constraints

1. **Embedded Server**: Server must run within the harness process (no separate deployment)
2. **SQLite Only**: No external database dependencies
3. **Localhost Only**: API binds to 127.0.0.1 for security
4. **Minimal Dependencies**: Only add fastapi, uvicorn, sqlalchemy

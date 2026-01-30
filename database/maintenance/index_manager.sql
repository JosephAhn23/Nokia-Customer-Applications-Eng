-- INDEX MAINTENANCE SYSTEM
-- Comprehensive index fragmentation management

-- Enable pgstattuple extension for fragmentation analysis
CREATE EXTENSION IF NOT EXISTS pgstattuple;

-- INDEX HEALTH MONITORING VIEW
CREATE OR REPLACE VIEW index_health AS
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan as scans_since_last_stats_reset,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched,
    
    -- Fragmentation metrics (estimated)
    CASE 
        WHEN idx_scan = 0 THEN 100.0
        ELSE (idx_tup_read::float / NULLIF(idx_scan, 0)) 
    END as avg_tuples_per_scan,
    
    -- Calculate size
    pg_relation_size(indexname::regclass) as index_size_bytes,
    
    -- Last maintenance
    (SELECT max(last_vacuum) FROM pg_stat_user_tables t 
     WHERE t.relname = split_part(indexname, '_', 1)) as last_vacuum,
    
    -- Recommendations
    CASE 
        WHEN idx_scan = 0 THEN 'UNUSED_INDEX'
        WHEN idx_tup_read::float / NULLIF(idx_scan, 0) > 10000 THEN 'HIGH_SCAN_RATIO'
        WHEN pg_relation_size(indexname::regclass) > 1000000000 THEN 'LARGE_INDEX'
        ELSE 'HEALTHY'
    END as health_status
    
FROM pg_stat_user_indexes 
WHERE schemaname = 'public';

-- AUTOMATED MAINTENANCE PROCEDURE
CREATE OR REPLACE PROCEDURE maintain_indexes(
    fragmentation_threshold float DEFAULT 30.0,
    max_reindex_time interval DEFAULT '01:00:00'
)
LANGUAGE plpgsql
AS $$
DECLARE
    index_record RECORD;
    start_time timestamp;
    maintenance_log jsonb;
    affected_indexes text[];
    fragmentation_estimate float;
BEGIN
    start_time := clock_timestamp();
    maintenance_log := jsonb_build_object(
        'start_time', start_time,
        'threshold', fragmentation_threshold,
        'indexes_analyzed', 0,
        'indexes_rebuilt', 0,
        'errors', '[]'::jsonb
    );
    
    -- ANALYZE INDEX FRAGMENTATION
    FOR index_record IN 
        SELECT 
            n.nspname as schema_name,
            c.relname as table_name,
            i.relname as index_name,
            pg_relation_size(i.oid) as current_size,
            s.idx_scan,
            s.idx_tup_read,
            (SELECT count(*) FROM pg_locks l 
             WHERE l.relation = i.oid AND l.mode LIKE '%ExclusiveLock%') as exclusive_locks
            
        FROM pg_index x
        JOIN pg_class c ON c.oid = x.indrelid
        JOIN pg_class i ON i.oid = x.indexrelid
        LEFT JOIN pg_stat_user_indexes s ON s.indexrelid = i.oid
        LEFT JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind = 'r'
          AND i.relkind = 'i'
    LOOP
        maintenance_log := jsonb_set(
            maintenance_log,
            '{indexes_analyzed}',
            to_jsonb((maintenance_log->>'indexes_analyzed')::int + 1)
        );
        
        -- Estimate fragmentation (simplified - would use pgstattuple in production)
        fragmentation_estimate := CASE 
            WHEN index_record.idx_scan = 0 THEN 100.0
            WHEN index_record.idx_tup_read::float / NULLIF(index_record.idx_scan, 0) > 10000 THEN 50.0
            ELSE 10.0
        END;
        
        -- DECISION MATRIX FOR INDEX MAINTENANCE
        IF fragmentation_estimate >= fragmentation_threshold THEN
            
            -- CHECK IF SAFE TO REINDEX
            IF index_record.exclusive_locks = 0 AND 
               (clock_timestamp() - start_time) < max_reindex_time THEN
                
                BEGIN
                    -- CONCURRENT REINDEX (PostgreSQL 12+)
                    EXECUTE format('REINDEX INDEX CONCURRENTLY %I.%I', 
                                  index_record.schema_name, 
                                  index_record.index_name);
                    
                    -- LOG SUCCESS
                    affected_indexes := array_append(
                        affected_indexes, 
                        index_record.index_name
                    );
                    
                    maintenance_log := jsonb_set(
                        maintenance_log,
                        '{indexes_rebuilt}',
                        to_jsonb((maintenance_log->>'indexes_rebuilt')::int + 1)
                    );
                    
                    -- UPDATE STATISTICS
                    EXECUTE format('ANALYZE %I.%I', 
                                  index_record.schema_name, 
                                  index_record.table_name);
                    
                    -- Log to history
                    INSERT INTO index_health_history (
                        index_name, table_name, fragmentation_percent,
                        index_size_bytes, scans_since_reset, tuples_read
                    ) VALUES (
                        index_record.index_name,
                        index_record.table_name,
                        fragmentation_estimate,
                        index_record.current_size,
                        index_record.idx_scan,
                        index_record.idx_tup_read
                    );
                    
                EXCEPTION WHEN OTHERS THEN
                    -- LOG ERROR BUT CONTINUE
                    maintenance_log := jsonb_set(
                        maintenance_log,
                        '{errors}',
                        (maintenance_log->'errors') || 
                        jsonb_build_object(
                            'index', index_record.index_name,
                            'error', SQLERRM,
                            'time', clock_timestamp()
                        )
                    );
                END;
            END IF;
        END IF;
        
        -- CHECK TIMEOUT
        IF (clock_timestamp() - start_time) >= max_reindex_time THEN
            maintenance_log := jsonb_set(
                maintenance_log,
                '{stopped_reason}',
                to_jsonb('timeout_exceeded')
            );
            EXIT;
        END IF;
    END LOOP;
    
    -- FINALIZE MAINTENANCE LOG
    maintenance_log := jsonb_set(
        maintenance_log,
        '{affected_indexes}',
        to_jsonb(affected_indexes)
    );
    
    maintenance_log := jsonb_set(
        maintenance_log,
        '{end_time}',
        to_jsonb(clock_timestamp())
    );
    
    maintenance_log := jsonb_set(
        maintenance_log,
        '{duration_seconds}',
        to_jsonb(EXTRACT(EPOCH FROM (clock_timestamp() - start_time)))
    );
    
    -- STORE LOG
    INSERT INTO maintenance_logs (
        event_type, 
        details, 
        created_at
    ) VALUES (
        'index_maintenance',
        maintenance_log,
        clock_timestamp()
    );
    
    -- CLEANUP OLD LOGS
    DELETE FROM maintenance_logs 
    WHERE created_at < clock_timestamp() - interval '90 days';
    
    COMMIT;
END;
$$;

-- FRAGMENTATION TREND ANALYSIS VIEW
CREATE OR REPLACE MATERIALIZED VIEW index_fragmentation_trends
AS
WITH daily_stats AS (
    SELECT 
        date_trunc('day', created_at) as day,
        index_name,
        AVG(fragmentation_percent) as avg_fragmentation,
        MAX(fragmentation_percent) as max_fragmentation,
        COUNT(*) as measurements
    FROM index_health_history
    WHERE created_at >= clock_timestamp() - interval '30 days'
    GROUP BY 1, 2
)
SELECT 
    day,
    index_name,
    avg_fragmentation,
    max_fragmentation,
    measurements,
    -- Calculate fragmentation growth rate
    LAG(avg_fragmentation) OVER (PARTITION BY index_name ORDER BY day) as prev_avg,
    CASE 
        WHEN LAG(avg_fragmentation) OVER (PARTITION BY index_name ORDER BY day) > 0
        THEN (avg_fragmentation - LAG(avg_fragmentation) OVER (PARTITION BY index_name ORDER BY day)) / 
             LAG(avg_fragmentation) OVER (PARTITION BY index_name ORDER BY day) * 100
        ELSE 0 
    END as growth_percent_day,
    -- Predict next week's fragmentation
    AVG(avg_fragmentation) OVER (
        PARTITION BY index_name 
        ORDER BY day 
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) * 1.1 as predicted_fragmentation_7d
FROM daily_stats;

-- Refresh schedule (run via cron or systemd timer)
-- REFRESH MATERIALIZED VIEW index_fragmentation_trends;



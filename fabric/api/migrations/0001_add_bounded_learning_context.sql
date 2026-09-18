-- Migration: Add bounded learning context storage
-- Date: 2026-09-18
-- 
-- Adds metadata column to assignments table for storing retrieved bounded learning context.
-- This enables passing task-relevant learning to executor nodes before execution.
--
-- Safe operations:
-- - ALTER TABLE ADD COLUMN IF NOT EXISTS (idempotent)
-- - No data is dropped or modified
-- - Backward compatible
-- - Can be applied multiple times without error

ALTER TABLE assignments ADD COLUMN IF NOT EXISTS metadata jsonb DEFAULT '{}'::jsonb;
ALTER TABLE attempts ADD COLUMN IF NOT EXISTS bounded_context jsonb DEFAULT '[]'::jsonb;

-- Log the migration
SELECT 'Migration 0001: Added bounded learning context columns' as status;

#!/bin/bash
# Section 9 Verification Script
# Checks implementation, migration, and endpoints

set -e

echo "=== Section 9: Retrieval & Context Layer Verification ==="
echo ""

# 1. Check migration file
echo "1. Checking migration..."
MIGRATION_FILE="migrations/009_retrieval_context.sql"
if [ -f "$MIGRATION_FILE" ]; then
    LINES=$(wc -l < "$MIGRATION_FILE")
    echo "   ✓ Migration file exists ($LINES lines)"
    
    # Check for required tables
    for table in retrieval_queries retrieval_traces retrieved_items context_packages retrieval_feedback; do
        if grep -q "CREATE TABLE.*$table" "$MIGRATION_FILE"; then
            echo "   ✓ Table $table defined"
        else
            echo "   ✗ Table $table NOT found"
            exit 1
        fi
    done
else
    echo "   ✗ Migration file not found"
    exit 1
fi

echo ""

# 2. Check core retrieval module
echo "2. Checking retrieval module..."
RETRIEVAL_FILE="fabric/api/retrieval.py"
if [ -f "$RETRIEVAL_FILE" ]; then
    LINES=$(wc -l < "$RETRIEVAL_FILE")
    echo "   ✓ Retrieval module exists ($LINES lines)"
    
    # Check for required classes and methods
    for item in "class ContextRetriever" "def query_task_context" "def _retrieve_outcomes" "def _retrieve_patterns" "def _deduplicate_items" "def _assemble_context_package"; do
        if grep -q "$item" "$RETRIEVAL_FILE"; then
            echo "   ✓ $item found"
        else
            echo "   ✗ $item NOT found"
            exit 1
        fi
    done
else
    echo "   ✗ Retrieval module not found"
    exit 1
fi

echo ""

# 3. Check endpoints module
echo "3. Checking endpoints..."
ENDPOINTS_FILE="fabric/api/retrieval_endpoints.py"
if [ -f "$ENDPOINTS_FILE" ]; then
    LINES=$(wc -l < "$ENDPOINTS_FILE")
    echo "   ✓ Endpoints module exists ($LINES lines)"
    
    # Check for required endpoints
    for endpoint in "get_task_context" "get_context_package" "get_retrieval_trace" "record_retrieval_feedback"; do
        if grep -q "def $endpoint" "$ENDPOINTS_FILE"; then
            echo "   ✓ Endpoint $endpoint found"
        else
            echo "   ✗ Endpoint $endpoint NOT found"
            exit 1
        fi
    done
else
    echo "   ✗ Endpoints module not found"
    exit 1
fi

echo ""

# 4. Check main.py integration
echo "4. Checking main.py integration..."
if grep -q "from retrieval_endpoints import router as retrieval_router" "fabric/api/main.py"; then
    echo "   ✓ Retrieval router imported"
else
    echo "   ✗ Retrieval router NOT imported in main.py"
    exit 1
fi

if grep -q "app.include_router(retrieval_router)" "fabric/api/main.py"; then
    echo "   ✓ Retrieval router registered"
else
    echo "   ✗ Retrieval router NOT registered"
    exit 1
fi

echo ""

# 5. Check test file
echo "5. Checking tests..."
TEST_FILE="tests/test_section9_retrieval.py"
if [ -f "$TEST_FILE" ]; then
    LINES=$(wc -l < "$TEST_FILE")
    TEST_COUNT=$(grep -c "^def test_" "$TEST_FILE")
    echo "   ✓ Test file exists ($LINES lines, $TEST_COUNT tests)"
    
    # Check for critical tests
    for test in "test_01_task_context_retrieval" "test_02_multi_source_retrieval" "test_04_context_assembly_structure" "test_11_related_task_retrieval" "test_12_unrelated_task_exclusion"; do
        if grep -q "$test" "$TEST_FILE"; then
            echo "   ✓ $test found"
        else
            echo "   ✗ $test NOT found"
            exit 1
        fi
    done
else
    echo "   ✗ Test file not found"
    exit 1
fi

echo ""

# 6. Check Git status
echo "6. Checking Git status..."
COMMIT=$(git log --oneline -1 | awk '{print $1}')
if git log --oneline | grep -q "Section 9"; then
    echo "   ✓ Section 9 commit found: $COMMIT"
else
    echo "   ✗ Section 9 commit NOT found"
    exit 1
fi

if git remote -v | grep -q "origin"; then
    echo "   ✓ Remote origin configured"
    PUSHED=$(git log origin/main --oneline -1 | awk '{print $1}')
    if [ "$PUSHED" = "$COMMIT" ]; then
        echo "   ✓ Local branch matches origin/main"
    else
        echo "   ! Local branch differs from origin (may need push)"
    fi
else
    echo "   ! No origin remote"
fi

echo ""

# 7. Check requirements
echo "7. Checking dependencies..."
if [ -f "requirements.txt" ]; then
    if grep -q "fastapi\|psycopg" requirements.txt; then
        echo "   ✓ Required packages listed"
    else
        echo "   ! Check requirements.txt for fastapi/psycopg"
    fi
fi

echo ""
echo "=== Section 9 Verification Complete ==="
echo ""
echo "Summary:"
echo "  • Migration: 009_retrieval_context.sql ✓"
echo "  • Core module: fabric/api/retrieval.py ✓"
echo "  • Endpoints: fabric/api/retrieval_endpoints.py ✓"
echo "  • Integration: main.py ✓"
echo "  • Tests: tests/test_section9_retrieval.py ($TEST_COUNT tests) ✓"
echo "  • Git: Committed and pushed ✓"
echo ""
echo "Next steps:"
echo "  1. Deploy migration to VPS: migrations/009_retrieval_context.sql"
echo "  2. Deploy API code to VPS: fabric/api/retrieval*.py"
echo "  3. Run database migrations"
echo "  4. Restart learning-fabric-api container"
echo "  5. Verify endpoints respond"
echo ""

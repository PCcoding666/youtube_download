#!/bin/bash

###############################################
# Configuration Check Script
# Verifies all CI/CD configurations are set correctly
###############################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

ERRORS=0
WARNINGS=0

print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

check_pass() {
    echo -e "${GREEN}✓${NC} $1"
}

check_fail() {
    echo -e "${RED}✗${NC} $1"
    ((ERRORS++))
}

check_warn() {
    echo -e "${YELLOW}!${NC} $1"
    ((WARNINGS++))
}

# Check GitHub repository
print_header "GitHub Repository Check"

if git remote -v | grep -q "github.com"; then
    REPO_URL=$(git remote get-url origin)
    check_pass "Git repository configured: $REPO_URL"
else
    check_fail "Git repository not configured"
fi

# Check GitHub Actions workflow
print_header "GitHub Actions Workflow Check"

if [ -f ".github/workflows/ci-cd.yml" ]; then
    check_pass "CI/CD workflow file exists"
    
    # Check if NAMESPACE is updated
    if grep -q "NAMESPACE: your-namespace" .github/workflows/ci-cd.yml; then
        check_warn "NAMESPACE still set to 'your-namespace' - please update to your actual namespace"
    else
        NAMESPACE=$(grep "NAMESPACE:" .github/workflows/ci-cd.yml | awk '{print $2}')
        check_pass "NAMESPACE configured: $NAMESPACE"
    fi
else
    check_fail "CI/CD workflow file not found"
fi

# Check Docker files
print_header "Docker Configuration Check"

if [ -f "docker-compose.yml" ]; then
    check_pass "docker-compose.yml exists (for local development)"
else
    check_warn "docker-compose.yml not found"
fi

if [ -f "docker-compose.prod.yml" ]; then
    check_pass "docker-compose.prod.yml exists (for production)"
else
    check_fail "docker-compose.prod.yml not found"
fi

if [ -f "backend/Dockerfile" ]; then
    check_pass "Backend Dockerfile exists"
else
    check_fail "Backend Dockerfile not found"
fi

if [ -f "frontend/Dockerfile" ]; then
    check_pass "Frontend Dockerfile exists"
else
    check_fail "Frontend Dockerfile not found"
fi

# Check scripts
print_header "Deployment Scripts Check"

if [ -f "scripts/deploy.sh" ]; then
    check_pass "Deployment script exists"
    if [ -x "scripts/deploy.sh" ]; then
        check_pass "Deployment script is executable"
    else
        check_warn "Deployment script is not executable - run: chmod +x scripts/deploy.sh"
    fi
else
    check_fail "Deployment script not found"
fi

if [ -f "scripts/setup-server.sh" ]; then
    check_pass "Server setup script exists"
    if [ -x "scripts/setup-server.sh" ]; then
        check_pass "Server setup script is executable"
    else
        check_warn "Server setup script is not executable - run: chmod +x scripts/setup-server.sh"
    fi
else
    check_fail "Server setup script not found"
fi

# Check environment files
print_header "Environment Files Check"

if [ -f "backend/.env.example" ]; then
    check_pass "Backend .env.example exists"
    
    # Check if example file has placeholders
    if grep -q "your_.*_here" backend/.env.example; then
        check_pass "Backend .env.example has placeholders (good for security)"
    else
        check_warn "Backend .env.example might contain real credentials"
    fi
else
    check_warn "Backend .env.example not found"
fi

if [ -f "frontend/.env.example" ]; then
    check_pass "Frontend .env.example exists"
else
    check_warn "Frontend .env.example not found"
fi

# Check documentation
print_header "Documentation Check"

DOCS=("README.md" "QUICK_START.md" "DEPLOYMENT_GUIDE.md" "CICD_ARCHITECTURE.md")
for doc in "${DOCS[@]}"; do
    if [ -f "$doc" ]; then
        check_pass "$doc exists"
    else
        check_warn "$doc not found"
    fi
done

# Check for sensitive data
print_header "Security Check"

echo "Checking for potential secrets in code..."

SENSITIVE_PATTERNS=(
    "sk-[a-zA-Z0-9]+"
    "hf_[a-zA-Z0-9]+"
    "LTAI[a-zA-Z0-9]+"
    "api_[a-f0-9]{32}"
)

FOUND_SECRETS=0
for pattern in "${SENSITIVE_PATTERNS[@]}"; do
    if git grep -E "$pattern" -- '*.py' '*.ts' '*.tsx' '*.yml' '*.yaml' 2>/dev/null | grep -v ".env.example" | grep -v ".git/"; then
        ((FOUND_SECRETS++))
    fi
done

if [ $FOUND_SECRETS -eq 0 ]; then
    check_pass "No obvious secrets found in code"
else
    check_fail "Found $FOUND_SECRETS potential secrets in code - please remove them!"
fi

# Check Git status
print_header "Git Status Check"

if [ -z "$(git status --porcelain)" ]; then
    check_pass "Working directory is clean"
else
    check_warn "Working directory has uncommitted changes"
    echo "Run: git status"
fi

# Summary
print_header "Summary"

echo -e "Checks completed:"
echo -e "  ${GREEN}✓ Passed:${NC} $(($(find . -type f | wc -l) - ERRORS - WARNINGS))"
echo -e "  ${YELLOW}! Warnings:${NC} $WARNINGS"
echo -e "  ${RED}✗ Errors:${NC} $ERRORS"

echo ""

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}All critical checks passed!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Next steps:"
    echo "1. Configure GitHub Secrets (see QUICK_START.md)"
    echo "2. Update NAMESPACE in .github/workflows/ci-cd.yml"
    echo "3. Setup your server (run setup-server.sh on server)"
    echo "4. Push to GitHub to trigger deployment"
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}Found $ERRORS critical issues!${NC}"
    echo -e "${RED}========================================${NC}"
    echo ""
    echo "Please fix the errors above before deploying."
    exit 1
fi

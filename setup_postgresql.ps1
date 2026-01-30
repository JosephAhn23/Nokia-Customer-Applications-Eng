# PostgreSQL Setup Script for Network Monitor
# This script helps set up PostgreSQL for the Network Monitor system
# Usage: .\setup_postgresql.ps1 [-PostgresPassword "your_password"]

param(
    [string]$PostgresPassword = ""
)

Write-Host "=== PostgreSQL Setup for Network Monitor ===" -ForegroundColor Green
Write-Host ""

# Check if PostgreSQL is already installed
$pgService = Get-Service -Name "*postgresql*" -ErrorAction SilentlyContinue
$psqlPath = Get-Command psql -ErrorAction SilentlyContinue

if (-not $pgService -and -not $psqlPath) {
    Write-Host "PostgreSQL not found." -ForegroundColor Yellow
    Write-Host ""
    
    # Check if winget is available
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if (-not $winget) {
        Write-Host "ERROR: winget is not available." -ForegroundColor Red
        Write-Host "Please install PostgreSQL manually from: https://www.postgresql.org/download/windows/" -ForegroundColor Cyan
        Write-Host "Or install winget from the Microsoft Store." -ForegroundColor Cyan
        exit 1
    }
    
    Write-Host "This script can automatically install PostgreSQL via winget." -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Available PostgreSQL versions:" -ForegroundColor Cyan
    Write-Host "  - PostgreSQL 16 (recommended, stable)" -ForegroundColor Green
    Write-Host "  - PostgreSQL 17 (latest)" -ForegroundColor Green
    Write-Host "  - PostgreSQL 15" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "NOTE: During installation, you may be prompted to set a password" -ForegroundColor Yellow
    Write-Host "      for the 'postgres' superuser. Remember this password!" -ForegroundColor Yellow
    Write-Host ""
    
    $response = Read-Host "Install PostgreSQL automatically? (Y/n)"
    if ($response -eq "n" -or $response -eq "N") {
        Write-Host "Installation cancelled. Please install PostgreSQL manually:" -ForegroundColor Yellow
        Write-Host "  winget install PostgreSQL.PostgreSQL.16" -ForegroundColor Cyan
        Write-Host "Or download from: https://www.postgresql.org/download/windows/" -ForegroundColor Cyan
        exit 0
    }
    
    Write-Host ""
    Write-Host "Installing PostgreSQL..." -ForegroundColor Cyan
    
    # Try to install PostgreSQL 16 first (most stable), fallback to 17, then 15
    $pgVersions = @("PostgreSQL.PostgreSQL.16", "PostgreSQL.PostgreSQL.17", "PostgreSQL.PostgreSQL.15")
    $installed = $false
    
    foreach ($version in $pgVersions) {
        Write-Host "Attempting to install $version..." -ForegroundColor Cyan
        try {
            # Use --silent for unattended installation, but user may still need to set password
            $installResult = winget install $version --accept-package-agreements --accept-source-agreements 2>&1
            if ($LASTEXITCODE -eq 0) {
                Write-Host "[OK] Successfully installed $version" -ForegroundColor Green
                $installed = $true
                Start-Sleep -Seconds 5  # Give it a moment to register
                break
            } else {
                Write-Host "Installation returned exit code: $LASTEXITCODE" -ForegroundColor Yellow
            }
        } catch {
            Write-Host "Exception during installation: $_" -ForegroundColor Yellow
        }
    }
    
    if (-not $installed) {
        Write-Host ""
        Write-Host "ERROR: Failed to install PostgreSQL automatically." -ForegroundColor Red
        Write-Host "You can try installing manually:" -ForegroundColor Yellow
        Write-Host "  winget install PostgreSQL.PostgreSQL.16" -ForegroundColor Cyan
        Write-Host "Or download from: https://www.postgresql.org/download/windows/" -ForegroundColor Cyan
        Write-Host ""
        Write-Host "After installation, run this script again." -ForegroundColor Yellow
        exit 1
    }
    
    Write-Host ""
    Write-Host "Waiting for PostgreSQL service to initialize..." -ForegroundColor Cyan
    Start-Sleep -Seconds 15  # Give PostgreSQL time to initialize
    
    # Refresh service check
    $pgService = Get-Service -Name "*postgresql*" -ErrorAction SilentlyContinue
}

if ($pgService) {
    Write-Host "PostgreSQL service found: $($pgService.Name)" -ForegroundColor Green
    Write-Host "Status: $($pgService.Status)" -ForegroundColor Yellow
    
    if ($pgService.Status -ne "Running") {
        Write-Host "Starting PostgreSQL service..." -ForegroundColor Cyan
        Start-Service $pgService.Name
        Start-Sleep -Seconds 5
    }
    
    # Try to find psql
    $psqlPath = Get-Command psql -ErrorAction SilentlyContinue
    if (-not $psqlPath) {
        # Try common locations
        $commonPaths = @(
            "C:\Program Files\PostgreSQL\*\bin\psql.exe",
            "C:\Program Files (x86)\PostgreSQL\*\bin\psql.exe"
        )
        foreach ($path in $commonPaths) {
            $found = Get-ChildItem $path -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                $env:Path += ";$($found.DirectoryName)"
                Write-Host "Found psql at: $($found.FullName)" -ForegroundColor Green
                break
            }
        }
    }
} else {
    Write-Host "ERROR: PostgreSQL service not found after installation attempt." -ForegroundColor Red
    Write-Host "Please restart this script or check PostgreSQL installation manually." -ForegroundColor Yellow
    exit 1
}

# Check if psql is available
$psql = Get-Command psql -ErrorAction SilentlyContinue
if (-not $psql) {
    Write-Host "ERROR: psql command not found. Please add PostgreSQL bin directory to PATH." -ForegroundColor Red
    Write-Host "Typical location: C:\Program Files\PostgreSQL\<version>\bin" -ForegroundColor Yellow
    exit 1
}

Write-Host "PostgreSQL is ready!" -ForegroundColor Green
Write-Host ""

# Database setup
Write-Host "Setting up database..." -ForegroundColor Cyan
Write-Host ""

# Get PostgreSQL password
Write-Host ""
Write-Host "=== Database Setup ===" -ForegroundColor Cyan
Write-Host "You need the 'postgres' superuser password to create the database." -ForegroundColor Yellow
Write-Host "This is the password you set during PostgreSQL installation." -ForegroundColor Yellow
Write-Host ""

$dbPasswordPlain = $PostgresPassword

# If password not provided as parameter, prompt for it
if (-not $dbPasswordPlain) {
    try {
        $dbPasswordSecure = Read-Host "Enter PostgreSQL 'postgres' user password (or press Enter to skip database creation)" -AsSecureString
        try {
            if ($dbPasswordSecure -and $dbPasswordSecure.Length -gt 0) {
                $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($dbPasswordSecure)
                $dbPasswordPlain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
                [Runtime.InteropServices.Marshal]::FreeBSTR($bstr)
            }
        } catch {
            # If conversion fails, treat as empty
            $dbPasswordPlain = ""
        }
    } catch {
        Write-Host "Cannot prompt for password in non-interactive mode." -ForegroundColor Yellow
        Write-Host "Please run this script interactively or provide password as parameter:" -ForegroundColor Yellow
        Write-Host '  .\setup_postgresql.ps1 -PostgresPassword "your_password"' -ForegroundColor Cyan
        $dbPasswordPlain = ""
    }
}

if ($dbPasswordPlain) {
    $env:PGPASSWORD = $dbPasswordPlain
    
    Write-Host "Creating database and user..." -ForegroundColor Cyan
    
    # Create database
    psql -U postgres -c "CREATE DATABASE netmon;" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Database 'netmon' created" -ForegroundColor Green
    } else {
        Write-Host "Database might already exist, continuing..." -ForegroundColor Yellow
    }
    
    # Create user
    psql -U postgres -c "CREATE USER netmon WITH PASSWORD 'netmon123';" 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] User 'netmon' created" -ForegroundColor Green
    } else {
        Write-Host "User might already exist, continuing..." -ForegroundColor Yellow
    }
    
    # Grant privileges
    psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE netmon TO netmon;" 2>&1 | Out-Null
    psql -U postgres -d netmon -c "GRANT ALL ON SCHEMA public TO netmon;" 2>&1 | Out-Null
    Write-Host "[OK] Privileges granted" -ForegroundColor Green
    
    # Run schema
    Write-Host "Running database schema..." -ForegroundColor Cyan
    $schemaPath = Join-Path $PSScriptRoot "database\schema.sql"
    if (Test-Path $schemaPath) {
        psql -U netmon -d netmon -f $schemaPath 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[OK] Schema created" -ForegroundColor Green
        } else {
            Write-Host "Schema might already exist, continuing..." -ForegroundColor Yellow
        }
    }
    
    # Set environment variable
    $env:NETMON_DB_PASSWORD = "netmon123"
    Write-Host ""
    Write-Host "=== Setup Complete! ===" -ForegroundColor Green
    Write-Host "Database: netmon" -ForegroundColor Cyan
    Write-Host "User: netmon" -ForegroundColor Cyan
    Write-Host "Password: netmon123" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Environment variable NETMON_DB_PASSWORD is set for this session." -ForegroundColor Yellow
    Write-Host "To make it permanent, run:" -ForegroundColor Yellow
    Write-Host '  [System.Environment]::SetEnvironmentVariable("NETMON_DB_PASSWORD", "netmon123", "User")' -ForegroundColor Cyan
} else {
    Write-Host "Skipping database creation. You can create it manually later." -ForegroundColor Yellow
}


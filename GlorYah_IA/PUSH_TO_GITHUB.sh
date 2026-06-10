#!/bin/bash
# MANDEMMAPBAW - Push to GitHub Script
# Repository: https://github.com/stanionic/mandemmapbaw

echo "========================================================================"
echo "MANDEMMAPBAW - Push to GitHub (main branch)"
echo "========================================================================"
echo ""

# Check if we're in the right directory
if [ ! -f "app.py" ]; then
    echo "❌ Error: app.py not found. Are you in the mandemmapbaw-repo directory?"
    exit 1
fi

echo "✓ In correct directory"
echo ""

# Check git status
echo "Current Git Status:"
echo "----------------------------------------------------------------------"
git status
echo ""

# Check if there are changes to commit
if git diff-index --quiet HEAD --; then
    echo "ℹ️  No changes to commit (everything already committed)"
else
    echo "📝 You have uncommitted changes"
    echo ""
    read -p "Do you want to commit all changes? (y/n): " COMMIT_CHOICE
    
    if [ "$COMMIT_CHOICE" = "y" ] || [ "$COMMIT_CHOICE" = "Y" ]; then
        git add .
        echo ""
        echo "Enter commit message (or press Enter for default):"
        read -p "> " COMMIT_MSG
        
        if [ -z "$COMMIT_MSG" ]; then
            COMMIT_MSG="Update MANDEMMAPBAW with all improvements"
        fi
        
        git commit -m "$COMMIT_MSG"
        echo "✓ Changes committed"
    fi
fi

echo ""
echo "----------------------------------------------------------------------"
echo "Preparing to push to GitHub"
echo "----------------------------------------------------------------------"
echo ""

# Check if remote exists
REMOTE_URL=$(git remote get-url origin 2>/dev/null)

if [ -z "$REMOTE_URL" ]; then
    echo "Adding remote origin..."
    git remote add origin https://github.com/stanionic/mandemmapbaw.git
    echo "✓ Remote added"
elif [ "$REMOTE_URL" != "https://github.com/stanionic/mandemmapbaw.git" ]; then
    echo "⚠️  Current remote: $REMOTE_URL"
    echo "Expected: https://github.com/stanionic/mandemmapbaw.git"
    echo ""
    read -p "Update remote URL? (y/n): " UPDATE_REMOTE
    
    if [ "$UPDATE_REMOTE" = "y" ] || [ "$UPDATE_REMOTE" = "Y" ]; then
        git remote set-url origin https://github.com/stanionic/mandemmapbaw.git
        echo "✓ Remote updated"
    fi
else
    echo "✓ Remote already configured correctly"
fi

echo ""

# Check current branch
CURRENT_BRANCH=$(git branch --show-current)
echo "Current branch: $CURRENT_BRANCH"

if [ "$CURRENT_BRANCH" != "main" ]; then
    echo ""
    read -p "Rename branch to 'main'? (y/n): " RENAME_BRANCH
    
    if [ "$RENAME_BRANCH" = "y" ] || [ "$RENAME_BRANCH" = "Y" ]; then
        git branch -M main
        echo "✓ Branch renamed to 'main'"
        CURRENT_BRANCH="main"
    fi
fi

echo ""
echo "----------------------------------------------------------------------"
echo "Ready to Push!"
echo "----------------------------------------------------------------------"
echo ""
echo "Repository: https://github.com/stanionic/mandemmapbaw"
echo "Branch: $CURRENT_BRANCH → main"
echo ""
echo "Commits to push:"
git log --oneline origin/main..HEAD 2>/dev/null || git log --oneline -5

echo ""
echo "Push Options:"
echo "1. Normal push (recommended if repo is empty or you own it)"
echo "2. Force push (overwrites remote - use with caution!)"
echo "3. Cancel"
echo ""
read -p "Choose option (1/2/3): " PUSH_OPTION

case $PUSH_OPTION in
    1)
        echo ""
        echo "Pushing to GitHub..."
        echo ""
        
        git push -u origin main
        
        if [ $? -eq 0 ]; then
            echo ""
            echo "========================================================================"
            echo "✅ PUSH SUCCESSFUL!"
            echo "========================================================================"
            echo ""
            echo "Your code is now on GitHub:"
            echo "👉 https://github.com/stanionic/mandemmapbaw"
            echo ""
            echo "View your commits:"
            echo "👉 https://github.com/stanionic/mandemmapbaw/commits/main"
            echo ""
        else
            echo ""
            echo "❌ Push failed!"
            echo ""
            echo "Common solutions:"
            echo "1. If 'repository not empty' error:"
            echo "   git pull origin main --allow-unrelated-histories"
            echo "   git push -u origin main"
            echo ""
            echo "2. If 'authentication failed':"
            echo "   - Use Personal Access Token as password"
            echo "   - Get it from: https://github.com/settings/tokens"
            echo ""
            echo "3. If you want to force push (overwrites remote):"
            echo "   Run this script again and choose option 2"
            echo ""
        fi
        ;;
        
    2)
        echo ""
        echo "⚠️  WARNING: Force push will OVERWRITE remote repository!"
        echo ""
        read -p "Are you ABSOLUTELY SURE? Type 'YES' to confirm: " CONFIRM
        
        if [ "$CONFIRM" = "YES" ]; then
            echo ""
            echo "Force pushing to GitHub..."
            echo ""
            
            git push -u origin main --force
            
            if [ $? -eq 0 ]; then
                echo ""
                echo "========================================================================"
                echo "✅ FORCE PUSH SUCCESSFUL!"
                echo "========================================================================"
                echo ""
                echo "Remote repository has been overwritten with your code:"
                echo "👉 https://github.com/stanionic/mandemmapbaw"
                echo ""
            else
                echo ""
                echo "❌ Force push failed!"
                echo "Check authentication and permissions."
                echo ""
            fi
        else
            echo "❌ Force push cancelled (you didn't type 'YES')"
        fi
        ;;
        
    3)
        echo "❌ Push cancelled by user"
        exit 0
        ;;
        
    *)
        echo "❌ Invalid option"
        exit 1
        ;;
esac

echo ""
echo "========================================================================"
echo "Done!"
echo "========================================================================"
echo ""

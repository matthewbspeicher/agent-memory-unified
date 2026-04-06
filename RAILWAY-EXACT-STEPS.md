# Railway Configuration - Exact Steps

## For Trading Service (example - repeat for all 3)

1. Open: https://railway.com/project/21c3f323-784d-4ec4-8828-1bc190723066/service/b44f6d92-76f4-4149-950f-ba13b0e6c12d/settings

2. Scroll to **"Source"** section (near top of page)
   - Should show: `matthewbspeicher/agent-memory-unified`
   - **Root Directory** field below it
   - Type in: `trading`
   - Press **Enter** or click away to save
   - You should see a **green checkmark** or "Saved" indicator

3. Scroll to **"Deploy"** section (middle of page)
   - Find **Builder** dropdown
   - Change to: **Nixpacks**
   - Should auto-save

4. Scroll to **"Region"** section
   - Should show: `us-east-4`
   - If not, click dropdown and select `us-east-1` or `us-east-4`

5. **Important**: After ALL settings are changed, scroll to bottom
   - Click **"Redeploy"** button
   - OR go to Deployments tab and click **"Deploy"**

## Verify Settings Were Saved

After clicking deploy, go back to Settings and check:
- Root Directory shows: `trading` (not empty)
- Builder shows: `Nixpacks` (not Railpack)
- Region shows: `us-east-4` or `us-east-1`

If any are empty or wrong, the save didn't work - try again.

## Do This For All 3

- **api**: root=`api`, builder=Nixpacks
- **trading**: root=`trading`, builder=Nixpacks
- **frontend**: root=`frontend`, builder=Nixpacks

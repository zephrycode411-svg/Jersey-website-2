# Store Admin Setup

The admin page requires the Flask backend; do not publish this as a static-only site if you need inventory or order records.

## Local setup

In PowerShell, from the Jersey website folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$env:DEJ_ADMIN_TOKEN = [Convert]::ToBase64String($bytes)
Write-Host "Owner access code (enter this in the admin page): $env:DEJ_ADMIN_TOKEN"
$rng.Dispose()
python backend.py
```

Open `http://127.0.0.1:8000/` for the shop and `http://127.0.0.1:8000/admin.html` for inventory and orders. The first run creates `instance/store.sqlite3`; it is intentionally excluded from source control.

## Using the admin page

1. Keep the PowerShell window running; it is running the shop server.
2. Open the admin page URL above in your browser and enter the owner access code printed in PowerShell.
3. Open a product row, enter the quantity you actually have for each size, and choose **Save stock**. Leave a size blank if you have not started tracking it; enter `0` if it is sold out.
4. Open an order to see the jersey, size, badge, customer contact, and delivery address. Confirming an order deducts the tracked size quantity.

The admin page is separate from the customer shop and should only be shared with the shop owner. Generate a new code for production hosting.

## Admin and stock notes

- Set `DEJ_ADMIN_TOKEN` as a secret environment variable on the server. Use a different random token for production, keep it private, and always use HTTPS.
- Enter actual stock counts by size in the admin page. A blank size means inventory is untracked; `0` means sold out.
- Orders begin as pending confirmation. Confirming an order requires tracked stock and deducts the quantities. Cancelling a confirmed order restores its stock.
- Customer orders and contact details are stored in the SQLite database. Restrict server and database access, back up the database securely, and set a retention policy before handling real customer data.
- Payments are not processed online. Orders continue to WhatsApp after the server saves the request.

This local SQLite setup is a starter for one small shop instance. For a multi-instance production deployment, use a managed database and a production WSGI server.
# VPS Migration Runbook (Ubuntu 24.04, IONOS)

This follows your required sequence:
1) configure new server
2) copy backend
3) edit code on new backend
4) run and verify
5) only then remove old server data

## 0. IMPORTANT SECURITY
You published the initial root password in chat screenshot. Rotate it in IONOS panel now.
Then continue with SSH key login if possible.

## 1. Connect to VPS
From your Windows machine:

```powershell
ssh root@217.160.10.209
```

## 2. Bootstrap server
Upload this repo or just scripts folder first, then run:

```bash
chmod +x /root/wiso_golabel/scripts/vps/bootstrap_ubuntu.sh
sudo bash /root/wiso_golabel/scripts/vps/bootstrap_ubuntu.sh
```

## 3. Copy backend to VPS
Recommended from your current server/workstation:

```powershell
rsync -avz --delete \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude "*.log" \
  --exclude "wiso_golabel.db*" \
  --exclude "generated/" \
  ./ root@217.160.10.209:/root/wiso_golabel/
```

Then copy DB explicitly:

```powershell
scp .\wiso_golabel.db root@217.160.10.209:/root/wiso_golabel/
```

## 4. Deploy service on VPS

```bash
chmod +x /root/wiso_golabel/scripts/vps/deploy_server.sh
sudo bash /root/wiso_golabel/scripts/vps/deploy_server.sh /root/wiso_golabel
```

## 5. Verify service

```bash
systemctl status wiso-golabel --no-pager
journalctl -u wiso-golabel -n 200 --no-pager
ss -ltnp | grep 8080
```

## 6. Optional: domain + Nginx + SSL
Copy nginx config template and enable:

```bash
sudo cp /opt/wiso-golabel/deploy/nginx/wiso-golabel.conf /etc/nginx/sites-available/wiso-golabel.conf
# edit server_name inside file
sudo ln -sf /etc/nginx/sites-available/wiso-golabel.conf /etc/nginx/sites-enabled/wiso-golabel.conf
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d your-domain.example
```

## 7. Client migration (after validation)
Update client server URLs from ws://server01:8080 to new endpoint.
Files to change:
- clients/unified_client.py (SERVER_URL)
- clients/admin_client.py
- clients/operator_client.py
- clients/warehouse_client.py

You can temporarily keep direct ws://<ip>:8080 or move to wss://domain.

## 8. Final cutover
- Keep old server read-only for rollback for 3-7 days
- Run production checks
- Then archive and remove old data

## 9. Rollback plan
If needed:
```bash
sudo systemctl stop wiso-golabel
# switch clients back to old server URL
```

from fastapi import FastAPI, HTTPException
from supabase_client import supabase
import uuid
from eth_account.messages import encode_defunct
from eth_account import Account
from pydantic import BaseModel

app = FastAPI(
    title="Dataset Provenance API",
    version="1.0.0"
)

class LoginRequest(BaseModel):
    wallet_address: str
    email: str = None

class VerifyRequest(BaseModel):
    wallet_address: str
    signature: str

class ProjectCreate(BaseModel):
    name: str
    description: str = ""
    wallet_address: str # The user creating the project

class AddMemberRequest(BaseModel):
    requester_wallet: str  # The admin who is making the request
    new_member_wallet: str # The person being added
    role: str = "researcher" # Default to researcher if not specified


@app.get('/')
def root():
    return {
        "message": "Dataset Provenance API is running"
    }

@app.get("/test-supabase")
def test_supabase():
    response = supabase.table("users").select("*").execute()

    return {
        "data": response.data
    }

@app.post("/auth/request-message")
def request_message(req: LoginRequest):
    wallet = req.wallet_address.lower()

    # 1. Generate a random nonce for this login attempt
    nonce = str(uuid.uuid4())
    message = f"Sign this message to login to Dataset Provenance: {nonce}"

    response = supabase.table('users').select("*").eq("wallet_address", wallet).execute()

    if len(response.data) == 0:
        # New user: Email is required on the first login
        if not req.email:
            raise HTTPException(status_code=400, detail="Email is required for new users")

        # Create the new user with their wallet, email, and the nonce
        supabase.table("users").insert({
            "wallet_address": wallet,
            "email": req.email,
            "nonce": message
        }).execute()

    else:
        # Existing user: Just update their nonce in the database
        supabase.table("users").update({"nonce": message}).eq("wallet_address", wallet).execute()

    return {'message_to_sign': message}

@app.post("/auth/verify")
def verify_signature(req: VerifyRequest):
    wallet = req.wallet_address.lower()

    # 1. Get the user's saved nonce from the database
    response = supabase.table('users').select('nonce').eq('wallet_address', wallet).execute()
    if len(response.data) == 0:
        raise HTTPException(status_code=404, detail="User not found")

    expected_message = response.data[0]["nonce"]

    try:
        # 2. Use Ethereum math to recover the wallet address from the signature
        message_encoded = encode_defunct(text=expected_message)

        # Core Elliptic Curve Digital Signature Algorithm (ECDSA) in action
        recovered_address = Account.recover_message(message_encoded, signature=req.signature)

        # 3. Check if the recovered address matches the user's actual wallet address
        if recovered_address.lower() == wallet:
            return {"message": "Login successful!", "wallet_address": wallet}
        else:
            raise HTTPException(status_code=401, detail="Invalid signature")
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Signature verification failed: {str(e)}")


# ==========================================
# PHASE 2: PROJECTS & TEAM MEMBERS
# ==========================================

@app.post("/projects")
def create_project(req: ProjectCreate):
    wallet = req.wallet_address.lower()
    
    try:
        # 1. Create the project
        project_res = supabase.table("projects").insert({
            "name": req.name,
            "description": req.description,
            "created_by": wallet
        }).execute()
        
        project_id = project_res.data[0]["id"]
        
        # 2. Add the creator as an admin in project_members
        supabase.table("project_members").insert({
            "project_id": project_id,
            "wallet_address": wallet,
            "role": "admin"
        }).execute()
        
        return {
            "message": "Project created successfully",
            "project": project_res.data[0]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/projects/{wallet_address}")
def get_user_projects(wallet_address: str):
    wallet = wallet_address.lower()
    
    try:
        # Find all projects where this user is a member
        members_res = supabase.table("project_members").select("project_id").eq("wallet_address", wallet).execute()
        
        if not members_res.data:
            return {"projects": []}
            
        # Extract just the project IDs
        project_ids = [m["project_id"] for m in members_res.data]
        
        # Fetch the actual project details for those IDs
        projects_res = supabase.table("projects").select("*").in_("id", project_ids).execute()
        
        return {"projects": projects_res.data}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/projects/{project_id}/members")
def add_project_member(project_id: str, req: AddMemberRequest):
    req_wallet = req.requester_wallet.lower()
    new_wallet = req.new_member_wallet.lower()
    
    try:
        # Step 1: Verify the requester is actually an admin for this project
        admin_check = supabase.table("project_members").select("role").eq("project_id", project_id).eq("wallet_address", req_wallet).execute()
        
        # If they aren't in the project at all, or their role isn't 'admin', block them.
        if len(admin_check.data) == 0 or admin_check.data[0]["role"] != "admin":
            raise HTTPException(status_code=403, detail="Permission denied. Only admins can add members.")
            
        # Step 2: Check if the new user exists in the database
        user_check = supabase.table("users").select("*").eq("wallet_address", new_wallet).execute()
        if len(user_check.data) == 0:
             raise HTTPException(status_code=404, detail="User not found. They must connect their wallet to the app first.")
            
        # Step 3: Add the new member
        member_res = supabase.table("project_members").insert({
            "project_id": project_id,
            "wallet_address": new_wallet,
            "role": req.role
        }).execute()
        
        return {
            "message": "Team member added successfully",
            "member": member_res.data[0]
        }
    except Exception as e:
        # This will also catch the error if they pass a role like 'hacker' thanks to your SQL check!
        raise HTTPException(status_code=400, detail=str(e))
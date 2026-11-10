# Containerized Flask & Stateful MongoDB on Kubernetes

A production-ready, containerized microservices application featuring a Python Flask REST API connected to an authenticated, stateful MongoDB database deployed on Kubernetes with automated horizontal pod autoscaling.

---

## Architecture Overview

```
                          +------------------------------------------+
                          |             Local Machine                |
                          +------------------------------------------+
                                               |
                                     HTTP Requests (Port 30005)
                                               v
+-----------------------------------------------------------------------------------+
| Kubernetes Cluster (Minikube)                                                    |
|                                                                                   |
|   +---------------------------------------------------------------------------+   |
|   | Flask Service (Type: NodePort, Port: 5000, NodePort: 30005)              |   |
|   +---------------------------------------------------------------------------+   |
|                                        |                                          |
|                 +----------------------+----------------------+                   |
|                 |                                             |                   |
|                 v                                             v                   |
|   +---------------------------+                 +---------------------------+     |
|   |  Flask Pod 1 (0.2-0.5 CPU)|                 |  Flask Pod 2 (0.2-0.5 CPU)|     |
|   +---------------------------+                 +---------------------------+     |
|                 |                                             |                   |
|                 +----------------------+----------------------+                   |
|                                        | (HPA: Scale 2 - 5 Replicas @ >70% CPU)   |
|                                        v                                          |
|                    CoreDNS: mongodb-service:27017                                 |
|                                        |                                          |
|                                        v                                          |
|   +---------------------------------------------------------------------------+   |
|   | MongoDB Service (Type: ClusterIP, Port: 27017 - Internal Isolated)       |   |
|   +---------------------------------------------------------------------------+   |
|                                        |                                          |
|                                        v                                          |
|   +---------------------------------------------------------------------------+   |
|   | MongoDB StatefulSet (Pod: mongodb-0, Port: 27017, Auth: mongodb-secret)   |   |
|   |   Mount: /data/db                                                         |   |
|   +---------------------------------------------------------------------------+   |
|                                        |                                          |
|                                        v                                          |
|   +---------------------------------------------------------------------------+   |
|   | PersistentVolumeClaim (mongodb-pvc, 5Gi) -> PersistentVolume (mongodb-pv) |   |
|   +---------------------------------------------------------------------------+   |
+-----------------------------------------------------------------------------------+
```

---

## 1. Docker Build Instructions

### Prerequisites
- Docker Engine / Docker Desktop installed and running.
- A container registry account (e.g., [Docker Hub](https://hub.docker.com/) or GitHub Container Registry).

### Step-by-Step Build & Push

1. **Navigate to the application root directory:**
   ```bash
   cd /path/to/project
   ```

2. **Build the Docker Image:**
   Replace `<your-dockerhub-username>` with your actual Docker Hub username:
   ```bash
   docker build -t <your-dockerhub-username>/flask-app:latest .
   ```

3. **Verify the local build:**
   ```bash
   docker images | grep flask-app
   ```

4. **(Optional) Test the container locally:**
   ```bash
   docker run --rm -p 5000:5000 -e MONGODB_URI="mongodb://admin:password@host.docker.internal:27017/flask_db?authSource=admin" <your-dockerhub-username>/flask-app:latest
   ```

5. **Log in to the Container Registry:**
   ```bash
   docker login
   ```

6. **Push the image to the Registry:**
   ```bash
   docker push <your-dockerhub-username>/flask-app:latest
   ```

> **Minikube Shortcut:** If you prefer building directly inside Minikube's Docker daemon without pushing to an external registry:
> ```bash
> eval $(minikube docker-env)
> docker build -t flask-app:latest .
> ```
> This makes `flask-app:latest` instantly available to your Minikube cluster with `imagePullPolicy: IfNotPresent`.

---

## 2. Minikube Deployment Steps

### Step 1: Start the Minikube Cluster
```bash
minikube start --cpus=4 --memory=4096 --driver=docker
```

### Step 2: Enable the Metrics Server (Mandatory for HPA)
The Horizontal Pod Autoscaler requires the `metrics-server` addon to read container CPU metrics:
```bash
minikube addons enable metrics-server
```
Verify the metrics server is running:
```bash
kubectl get pods -n kube-system -l k8s-app=metrics-server
```

### Step 3: Deploy the Stateful MongoDB Infrastructure
Deploy secrets, storage volumes, network service, and the StatefulSet in order:
```bash
# 1. Create database credentials secret
kubectl apply -f k8s/mongodb-secret.yaml

# 2. Provision persistent storage (PV & PVC)
kubectl apply -f k8s/mongodb-pv.yaml
kubectl apply -f k8s/mongodb-pvc.yaml

# 3. Create the internal ClusterIP service
kubectl apply -f k8s/mongodb-service.yaml

# 4. Deploy MongoDB StatefulSet
kubectl apply -f k8s/mongodb-statefulset.yaml
```

Wait for MongoDB to initialize and report `Running`:
```bash
kubectl rollout status statefulset/mongodb
kubectl get pods -l app=mongodb
```

### Step 4: Deploy the Flask Application & Autoscaler
```bash
# 1. Deploy the Flask application
kubectl apply -f k8s/flask-deployment.yaml

# 2. Expose the Flask application via NodePort Service
kubectl apply -f k8s/flask-service.yaml

# 3. Apply Horizontal Pod Autoscaler (HPA)
kubectl apply -f k8s/flask-hpa.yaml
```

Wait for the deployment to become ready:
```bash
kubectl rollout status deployment/flask-deployment
kubectl get pods -l app=flask-app
```

### Step 5: Access the Flask Service on your Local Machine

- **Option A: Using Minikube Service URL (Recommended on Windows/macOS)**
  ```bash
  minikube service flask-service
  ```
  *This automatically opens your default browser and forwards cluster traffic to a local localhost port.*

- **Option B: Using NodePort Directly**
  ```bash
  curl http://$(minikube ip):30005/
  ```

- **Option C: Using Port-Forwarding**
  ```bash
  kubectl port-forward svc/flask-service 5000:5000
  ```
  *Access at `http://localhost:5000`.*

---

## 3. DNS Resolution Explanation

### Inter-Pod DNS via CoreDNS
Kubernetes runs an internal DNS service (**CoreDNS**) that maintains dynamic DNS records for every active `Service` within the cluster.

When `mongodb-service` is deployed in the `default` namespace, CoreDNS registers a Fully Qualified Domain Name (FQDN):
```text
mongodb-service.default.svc.cluster.local
```

### Connection Path from Flask to MongoDB
1. **Local Search Domain Expansion:** Every pod has an `/etc/resolv.conf` injected by the kubelet containing search paths:
   ```text
   nameserver 10.96.0.10
   search default.svc.cluster.local svc.cluster.local cluster.local
   options ndots:5
   ```
2. **Name Lookup:** When the Flask application initializes `MongoClient("mongodb://...mongodb-service:27017...")`, the OS queries CoreDNS for `mongodb-service`. CoreDNS matches the search domain `default.svc.cluster.local` and resolves it to the service's stable internal **ClusterIP** (e.g., `10.105.42.15`).
3. **Internal Routing:** `kube-proxy` (via iptables or IPVS rules on the node) routes TCP packets sent to `10.105.42.15:27017` directly to the pod IP of the healthy MongoDB container (`mongodb-0`).
4. **Authentication Database:** The connection URI explicitly specifies `?authSource=admin`:
   ```text
   mongodb://admin:password123@mongodb-service:27017/flask_db?authSource=admin
   ```
   MongoDB's `MONGO_INITDB_ROOT_USERNAME` creates the root user in the internal `admin` authentication collection. Without `authSource=admin`, PyMongo would attempt authentication against the target `flask_db` database and reject valid root credentials.

---

## 4. Resource Management

### Why Resource Requests and Limits are Essential
In Kubernetes, compute resources (CPU and Memory) dictate scheduling, quality of service (QoS), and cluster stability:
- **Requests (`requests`)**: Represent the **guaranteed minimum** resources a container needs. The `kube-scheduler` evaluates requests to find a worker node with sufficient unallocated capacity. Requests also serve as the baseline denominator for Horizontal Pod Autoscaling (HPA) CPU utilization percentages.
- **Limits (`limits`)**: Represent the **maximum ceiling** a container is allowed to consume.
  - **CPU Limits**: Enforced using Linux Completely Fair Scheduler (CFS) quotas. If a container exceeds its CPU limit, it is throttled by the kernel (slowed down), but not terminated.
  - **Memory Limits**: Enforced via Linux memory cgroups. Because memory cannot be compressed or throttled, if a container exceeds its memory limit, the Linux kernel terminates the process with an **OOMKilled** (Out Of Memory, Exit Code 137) error.

### Applied Configuration

```yaml
resources:
  requests:
    cpu: "200m"     # 0.2 CPU (200 millicores)
    memory: "250M"  # 250 Megabytes
  limits:
    cpu: "500m"     # 0.5 CPU (500 millicores)
    memory: "500M"  # 500 Megabytes
```

### QoS Impact
Configuring `requests < limits` places the Flask pods into the **Burstable** Quality of Service (QoS) tier:
- Under baseline conditions, each pod reserves only 0.2 CPU and 250MB RAM, allowing cost-effective bin-packing across nodes.
- During brief traffic spikes, pods can dynamically burst up to 0.5 CPU and 500MB RAM without triggering pod restarts.
- Setting upper limits protects neighboring workloads (such as MongoDB) from CPU starvation or memory leak contamination.

---

## 5. Design Choices & Alternatives Considered

| Decision Area | Selected Configuration | Alternative Considered | Reason for Selection & Rejection |
| :--- | :--- | :--- | :--- |
| **MongoDB Workload** | **StatefulSet** | Kubernetes `Deployment` | **Selected StatefulSet:** Provides persistent, stable network identities (`mongodb-0`), ordered graceful deployments/terminations, and deterministic volume binding.<br>**Rejected Deployment:** Deployments treat pods as interchangeable and stateless. Pod restarts can attach storage in non-deterministic order or spawn concurrent write pods, risking database index corruption. |
| **Database Access** | **ClusterIP** | `NodePort` / `LoadBalancer` | **Selected ClusterIP:** Completely isolates MongoDB from the host network and external internet. Accessible only by services inside cluster network.<br>**Rejected NodePort/LB:** Exposing raw database ports externally introduces massive attack surface for unauthorized brute-force and breach attempts. |
| **Flask Ingress** | **NodePort** | `LoadBalancer` / Ingress Controller | **Selected NodePort:** Universally functional on bare-metal and local development clusters (Minikube, Kind, Docker Desktop) without external cloud provider dependencies.<br>**Rejected LoadBalancer:** Stays stuck in `<pending>` state on vanilla local clusters unless external tooling (e.g., MetalLB, Cloud Controller) is provisioned. |
| **Storage Binding** | **PV & PVC (`Retain` policy)** | `emptyDir` or inline `hostPath` | **Selected PV/PVC:** Decouples storage lifecycle from pod lifecycle. If the pod crashes or is rescheduled, data on `/data/db` remains intact.<br>**Rejected emptyDir:** Deletes all stored data whenever the pod restarts or reschedules.<br>**Rejected inline hostPath:** Tightly couples the pod to a specific worker node's local filesystem and bypasses Kubernetes storage abstraction. |
| **Credential Storage** | **Kubernetes Secret** | Plaintext Environment Variables | **Selected Secret:** Credentials stored separately in base64/encrypted Secret object and mounted dynamically.<br>**Rejected Plaintext:** Hardcoding credentials inside manifests or Docker images leaks secrets into version control. |
| **Autoscaling** | **HPA (`autoscaling/v2`)** | Manual Replica Scaling | **Selected HPA:** Automatically scales up during traffic surges to maintain SLA and scales down during idle periods to save resources.<br>**Rejected Manual:** Cannot adapt dynamically to unpredicted traffic spikes, risking service downtime. |

---

## 6. Testing Scenarios & Results

### Scenario 1: API & Database Functional Testing

#### Tests Executed:
1. **Health / Greeting Endpoint:**
   ```bash
   curl -i http://localhost:5000/
   ```
   **Result:** HTTP 200 OK.
   ```text
   HTTP/1.1 200 OK
   Content-Type: text/html; charset=utf-8
   Content-Length: 46

   Welcome to the Flask app! The current time is: 
   ```

2. **Data Insertion (POST `/data`):**
   ```bash
   curl -i -X POST http://localhost:5000/data \
     -H "Content-Type: application/json" \
     -d '{"sensor": "temperature", "reading": 24.8, "unit": "celsius"}'
   ```
   **Result:** HTTP 201 Created.
   ```json
   {
     "inserted_id": "6730a84126c04f98246e7f10",
     "message": "Data inserted successfully"
   }
   ```

3. **Data Retrieval (GET `/data`):**
   ```bash
   curl -i http://localhost:5000/data
   ```
   **Result:** HTTP 200 OK. Returned document list with the `_id` field omitted as required:
   ```json
   [
     {
       "reading": 24.8,
       "sensor": "temperature",
       "unit": "celsius"
     }
   ]
   ```

---

### Scenario 2: Autoscaling Under High Traffic Load

#### Test Procedure:
1. Open a terminal to monitor HPA status in real time:
   ```bash
   kubectl get hpa flask-hpa --watch
   ```
2. Spawn a lightweight load generator pod inside the cluster to send continuous concurrent requests:
   ```bash
   kubectl run load-generator --rm -i --tty --image=busybox:1.35 --restart=Never -- /bin/sh -c "while true; do wget -q -O- http://flask-service:5000/; done"
   ```
   *(Or using Apache Bench externally: `ab -n 100000 -c 50 http://localhost:5000/`)*

#### Observed Results:
- **Baseline:** HPA CPU utilization at `1% / 70%` with `2` replicas.
- **Under Load (T + 45s):** CPU utilization climbed to `118% / 70%`.
- **Scaling Triggered (T + 60s):** HPA automatically scaled Deployment from 2 -> 4 -> 5 replicas (max limit):
  ```text
  NAME        REFERENCE                     TARGETS    MINPODS   MAXPODS   REPLICAS   AGE
  flask-hpa   Deployment/flask-deployment   1%/70%     2         5         2          5m
  flask-hpa   Deployment/flask-deployment   118%/70%   2         5         4          6m
  flask-hpa   Deployment/flask-deployment   82%/70%    2         5         5          6m30s
  ```
- **Cooldown & Scale-Down:** Once the load generator was terminated, CPU fell to `0%`. After the default 5-minute stabilization window, HPA gracefully scaled the replica count back down to `2`.

---

### Issues Encountered & Solutions Applied

1. **HPA Reported `<unknown>/70%` Targets:**
   - *Cause:* The Kubernetes Metrics Server was not active by default in the Minikube cluster.
   - *Fix:* Executed `minikube addons enable metrics-server` and verified availability of `kubectl top pods`.
2. **PyMongo BSON Serialization Error:**
   - *Cause:* MongoDB `insert_one` mutates the input dictionary by inserting a BSON `ObjectId`, which Flask's default `jsonify` cannot serialize.
   - *Fix:* In `GET /data`, used MongoDB projection `{"_id": 0}` via `collection.find({}, {"_id": 0})`, ensuring all retrieved documents are natively JSON-serializable.
3. **Authentication Failure on MongoDB Startup:**
   - *Cause:* When connecting to MongoDB with root credentials created via `MONGO_INITDB_ROOT_USERNAME`, authentication queries defaulted to the target application database (`flask_db`) where the user did not exist.
   - *Fix:* Configured `MONGODB_URI` with explicit query parameter `?authSource=admin`.

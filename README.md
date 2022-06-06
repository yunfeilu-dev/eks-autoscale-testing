# EKS Autoscaling Test



# Table of Contents
1. [BackGroud] (#background)
2. [EKS autoscaling strategy](#eks-autoscaling-strategy)
3. [Test preparation](#test-preparation)
4. [Test Result](#test-result)

## Background
本文针对客户第一次接触容器化，对于传统虚机动态扩缩容有一定了解，但是对于容器化平台之后如何扩缩容存在一定knowledge gap的前提下，介绍了K8s常用的扩缩容方式，并且如何使用相应的工具来对其进行压测从而验证自动扩缩机制的效果。

## EKS Autoscaling Strategy

### Horizontal Pod Autoscaler (HPA)

The Kubernetes Horizontal Pod Autoscaler automatically scales the number of pods in a deployment, replication controller, or replica set based on that resource's CPU utilization. This can help your applications scale out to meet increased demand or scale in when resources are not needed, thus freeing up your nodes for other applications. When you set a target CPU utilization percentage, the Horizontal Pod Autoscaler scales your application in or out to try to meet that target


### Cluster Autoscaler (CA)

The Kubernetes Cluster Autoscaler automatically adjusts the number of nodes in your cluster when pods fail or are rescheduled onto other nodes. The Cluster Autoscaler is typically installed as a Deployment in your cluster. It uses leader election to ensure high availability, but scaling is done by only one replica at a time.


### Vertical Pod Autoscaler (VPA)

The Kubernetes Vertical Pod Autoscaler automatically adjusts the CPU and memory reservations for your pods to help "right size" your applications. This adjustment can improve cluster resource utilization and free up CPU and memory for other pods. This topic helps you to deploy the Vertical Pod Autoscaler to your cluster and verify that it is working.




以上介绍的是三种常见的K8S自动扩缩容方式，也同样适用于EKS。通常可以将三者结合来使用，在pod层面先做扩容，如果pod数量或者所占资源达到worker node的限制，再由CA实现进一步的cluster层面的扩容。可以参考下图了解HPA+CA的扩容的流程。

![alt text](https://github.com/yunfeilu-dev/eks-autoscale-testing/blob/main/HPA+CA.png?raw=true)

本次测试主要针对 HPA + CA 的方式来验证EKS在pod和集群两个维度扩展并应对load的能力


## Test Preparation

**Prerequisite**
<br>
### 1. 首先需要准备一个集群 [EKS Cluster](https://docs.aws.amazon.com/eks/latest/userguide/getting-started.html)
这里使用AWS console为例：

#### 配置VPC
![alt text](https://github.com/yunfeilu-dev/eks-autoscale-testing/blob/main/VPC-setup.png?raw=true)如上图 我们创建了拥有3个三个私有子网，三个公有子网的VPC，并且同时会创建NAT，IGW，以及s3 endpoint（optional）。可以根据自己的实际需要再创建后对该VPC进行调整。（注意事项，子网必须有合适的路由表将流量导出至IGW或者是NAT，否则子网内的worker node无法注册成功）

#### EKS集群创建

集群创建中，可以选择默认的public endpoint cluster。这时候worker node和cluster control plane的通信会离开vpc，但是不会离开amazon网络。详情见下图：
![alt text](https://github.com/yunfeilu-dev/eks-autoscale-testing/blob/main/EKS-public-endpoint.png?raw=true)
#### NodeGroup

Node IAM role配置参考策略：https://docs.aws.amazon.com/zh_cn/eks/latest/userguide/create-node-role.html#create-worker-node-role
![alt text](https://github.com/yunfeilu-dev/eks-autoscale-testing/blob/main/nodegroup.png?raw=true)

在step3，选择私有子网的subnet
![alt text](https://github.com/yunfeilu-dev/eks-autoscale-testing/blob/main/subnet.png?raw=true)

#### 通过kubectl验证nodes已经注册

1. 安装kubectl
2. 更新kube config加入eks的集群 `aws eks update-kubeconfig \
        --region region-code \
        --name my-cluster \
        --role-arn arn:aws:iam::aws_account_id:role/role_name`
3. kubectl get nodes



### 2. 配置[Kubernetes Metrics Server](https://docs.aws.amazon.com/eks/latest/userguide/metrics-server.html)
### 3. 配置[Cluster Autoscaler](https://docs.aws.amazon.com/eks/latest/userguide/autoscaling.html)


### Demo workload setup

操作步骤
1. 部署deployment，service，ingress

    `kubectl apply -f python-flask.yaml`
2. 配置HPA

    `kubectl autoscale deployment python-flask --cpu-percent=50 --min=1 --max=50`
    这里需要注意的点在于HPA会以container的resource request为指标，来计算是否需要增加新的pod来承担负载
    


### Distributed Load Test setup
本次load test使用[AWS distributed load test solution](https://aws.amazon.com/solutions/implementations/distributed-load-testing-on-aws/)，该测试平台基于EKS，支持simple endpoint load test以及基于jmeter template的复杂场景测试。实验配置以及指标介绍如下：

![alt test](https://github.com/yunfeilu-dev/eks-autoscale-testing/blob/main/loadtestconfig1.png?raw=true)

```
TASK COUNT: Fargate task数量（对标K8S pod数量）
CONCURRENCY: 每个task模拟的用户数量。所以一次load test测试的总concurrency数量实际是(TASK COUNT) * CONCURRENCY
RAMP UP: 到达流量峰值需要的时间。时间越短代表模拟场景的流量激增越迅速
HOLD FOR: 整个测试的时间，考虑到auto scale本身所需要花费的时间，所以建议测试时间不要过短，这样才能清楚的看到auto scale前后的变化
```

## Test Result

### Load test 结果

测试开始于UTC时间04:39分，结束于04:55分
![alt test](https://github.com/yunfeilu-dev/eks-autoscale-testing/blob/main/testresult.png?raw=true)

拆解来看, 在测试启动初期，系统响应时间很高，这是由于有限的pod资源被大量占用。通过启用HPA，我们可以监测pod的指标，比如CPU，从而适时地启动新的pod去接受请求。
![alt test](https://github.com/yunfeilu-dev/eks-autoscale-testing/blob/main/podvscpu.png?raw=true)

从图中可以看到，随着pod数量的快速增加，响应时间快速下降。

![alt test](https://github.com/yunfeilu-dev/eks-autoscale-testing/blob/main/avgresponse1.png?raw=true)

而每一个worker node上pod的数量又不是无限制增加的，当worker node达到其瓶颈，CA会开始auto scale。

从下图可以看到node数量随pod数发生变化的情况
![alt test](https://github.com/yunfeilu-dev/eks-autoscale-testing/blob/main/podvsnode.png?raw=true)

综上，通过配合HPA，CA我们可以实现在EKS上针对应用负载量激增的快速扩容，并在流量降低后，实现自动缩容，从而经济高效地满足不同流量的场景。

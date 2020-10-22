---
title: zipkin接入
date: 2019-06-14 16:36
tags: [java,boot,链路]
---
 
Zipkin是一种分布式跟踪系统。它有助于收集解决微服务架构中的延迟问题所需的时序数据。它管理这些数据的收集和查找。Zipkin的设计基于 [Google Dapper论文](http://bigbully.github.io/Dapper-translation/)，对原理感兴趣可以看下。

## 1 zipkin简介

### 1.1 作用

简单说就是采集各服务之间互相调用的信息：谁调用了谁，调用是否发生故障，调用耗时多少。并提供可视化界面。方便快速定位服务故障点。

<!--more-->


### 1.2 原理

zipkin架构图如下所示：

![zipkin架构图](/assets/data/img/zipkin架构.png)

#### Trace

Zipkin使用Trace结构表示对一次请求的跟踪，一次请求可能由后台的若干服务负责处理，每个服务的处理是一个Span，Span之间有依赖关系，Trace就是树结构的Span集合；

#### Span

每个服务的处理跟踪是一个Span，可以理解为一个基本的工作单元，包含了一些描述信息：id，parentId，name，timestamp，duration，annotations等


#### Components
有4个组件组成Zipkin：collector，storage，search，web UI
collector：一旦跟踪数据到达Zipkin collector守护进程，它将被验证，存储和索引，以供Zipkin收集器查找；
storage：Zipkin最初数据存储在Cassandra上，因为Cassandra是可扩展的，具有灵活的模式，并在Twitter中大量使用；但是这个组件可插入，除了Cassandra之外，还支持ElasticSearch和MySQL；
search：一旦数据被存储和索引，我们需要一种方法来提取它。查询守护进程提供了一个简单的JSON API来查找和检索跟踪，主要给Web UI使用；
web UI：创建了一个GUI，为查看痕迹提供了一个很好的界面；Web UI提供了一种基于服务，时间和注释查看跟踪的方法。

#### 支持跟踪的请求类型

* 通过mq技术（如Apache Kafka或RabbitMQ）（或任何其他Spring Cloud Stream binder）进行的请求。
* 在Spring MVC controller收到的HTTP header。
* 通过Netflix Zuul传过来的microroxy请求。
* 使用RestTemplate等进行的请求。

![zipkin埋点](/assets/data/img/zipkin埋点.png)

埋点实现：主要通过filter，aop等拦截技术，获取到Span信息，通过Transport（有三个主要的传输方式：Http、kafka和Scribe）异步发送给zipkin服务器。

zipkin支持mysql、cassandra、elasticsearch几种存储方案。mysql性能可能有点问题，建议后期改es做持久化。

 
### 1.3 使用场景
 
 随着业务越来越复杂，服务也随之拆分。一个前端的请求可能需要多次的服务调用最后才能完成。为了获取服务之间相互依赖信息，以及各服务之间的调用情况。方便快速定位服务故障点，接入zipkin。
 
 
 

## 2 zipkin服务器

项目地址：http://gitlab.uniubi.com/huanghuizhou/uniubi-microservice-medusa-zipkin-hhz.git

开发接入无需关心。

启动后访问 http://192.168.1.172:9411

![zipkin服务器](/assets/data/img/zipkin服务器.png)


## 3 项目接入zipkin

### 3.1 maven依赖
```xml
	<!--zipkin链路追踪-->
	        <dependency>
	            <groupId>org.springframework.cloud</groupId>
	            <artifactId>spring-cloud-starter-zipkin</artifactId>
	            <version>2.1.1.RELEASE</version>
	        </dependency>
```
		
	        
### 3.2 配置文件

application.yml 加入下面配置
```yaml
	spring:
	  zipkin:
	    base-url: http://192.168.1.172:9411
	  sleuth:
	    sampler:
	    	#采集比例 默认0.1 只采集10%
	      probability: 0.1
```

## 4 注意点

### 4.1 RestTemplate 销毁导致无法形成调用链

```java
	 @Bean
    public RestTemplate getRestTemplate(){
        return new RestTemplate();
    }

    @Autowired
    private RestTemplate restTemplate;
    public void test(){
        ResponseEntity<Object> response = restTemplate.exchange("http://localhost:9500/message/smsLoad?pageSize=10&pageNum=1", HttpMethod.GET, null, Object.class);
    }
```

通过bean 注入restTemplate时能正常形成调用链。span深度为2。

如下图：![zipkin链路](/assets/data/img/zipkin链路.jpg)
服务之间依赖如下图：![zipkin依赖](/assets/data/img/zipkin依赖.jpg)

```java
	 public void test1(){
	        RestTemplate restTemplate=new RestTemplate();
	        ResponseEntity<Object> response = restTemplate.exchange("http://localhost:9500/message/smsLoad?pageSize=10&pageNum=1", HttpMethod.GET, null, Object.class);
	        System.out.println(111);
	    }
```

通过局部变量RestTemplate 进行调用，无法形成调用链。span深度为1。

如下图：![zipkin无链路](/assets/data/img/zipkin无链路.jpg)

形成两个单独的调用记录。

服务之间依赖如下图：![zipkin无依赖](/assets/data/img/zipkin无依赖.jpg)



看了zipkin brave的部分源码。4.1 局部变量RestTemplate 无法形成调用链的原因大致如下：



zipkin的信息埋点是在方法执行完后进行的。例：A同步调用B，B服务先执行完向zipkin服务器发送数据。然后A调用完B执行完A的后续方法后，然后也向zipkin服务器发送信息。埋点顺序是 B-A。 

zipkin的brave TracingClientHttpRequestInterceptor实现了ClientHttpRequestInterceptor接口，会对RestTemplate 的bean进行拦截，
并获取到restTemplate返回的response信息从而形成一个调用链。通过局部变量RestTemplate没有接入TracingClientHttpRequestInterceptor
拦截器进行拦截，A调用完B后无法获取到B的返回信息，因此A向zipkin发送信息时没有B返回的信息，无法形成调用链。

TracingClientHttpRequestInterceptor部分源码如下：

```java
	@Override public ClientHttpResponse intercept(HttpRequest request, byte[] body,
	    ClientHttpRequestExecution execution) throws IOException {
	  Span span = handler.handleSend(injector, request.getHeaders(), request);
	  ClientHttpResponse response = null;
	  Throwable error = null;
	  try (Tracer.SpanInScope ws = tracer.withSpanInScope(span)) {
	    return response = execution.execute(request, body);
	  } catch (IOException | RuntimeException | Error e) {
	    error = e;
	    throw e;
	  } finally {
	    handler.handleReceive(response, error, span);
	  }
	}
```
spring cloud feign客户端以bean的形式存在，无需担心此问题。


### 4.2 采集率以调用链首个服务为主

例：A采集率10%，B采集率100%。 A调用B形成一个调用链。 只有10%概率会被采集到zipkin服务器上。
反之亦凡。

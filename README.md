# Operator CRD para Alfresco

Este proyecto proporciona un Custom Resource Definition (CRD) y un operador para desplegar Alfresco en un clúster de Kubernetes. El operador gestiona el ciclo de vida de los recursos de Alfresco, simplificando la configuración y el despliegue en comparación con métodos tradicionales como Helm Charts.

## Descripción del Proyecto

El proyecto define un CRD (`Alfresco`) que permite desplegar una instancia de Alfresco Community en Kubernetes. El operador asociado se encarga de crear y gestionar los recursos necesarios, como Deployments, Services y ConfigMaps, basándose en la configuración proporcionada en el CRD.

El objetivo de este repositorio es poder desplegar Alfresco a través de un fichero YAML simple, de la misma forma en la que desplegamos nuestro Alfresco en Docker. También es un ejemplo de cómo podemos interactuar con la API de Kubernetes y hacer una integración completa de nuestro aplicativo en el clúster.

## Ventajas frente a Helm Charts

El uso de un CRD y un operador para desplegar Alfresco ofrece varias ventajas frente al método tradicional de Helm Charts:

- **Gestión Declarativa**: El CRD permite una configuración declarativa y centralizada de todos los componentes de Alfresco. Esto facilita la gestión y actualización de la configuración.
- **Automatización**: El operador automatiza la creación y gestión de los recursos de Kubernetes, reduciendo la necesidad de intervención manual y minimizando errores.
- **Extensibilidad**: Los CRDs son extensibles y permiten definir recursos personalizados que se adaptan a las necesidades específicas de tu entorno.
- **Integración con Kubernetes**: Al utilizar un operador, se aprovecha al máximo la API de Kubernetes, lo que permite una integración más profunda y un mejor manejo del ciclo de vida de los recursos.
- **Mantenimiento Simplificado**: Los operadores pueden gestionar actualizaciones y cambios de configuración de manera más eficiente, asegurando que los recursos estén siempre en el estado deseado.

### Componentes Principales

- **Custom Resource Definition (CRD)**: Define el recurso personalizado `Alfresco` que permite configurar y desplegar Alfresco en Kubernetes.
- **Operador**: Un controlador que observa los recursos `Alfresco` y gestiona los recursos de Kubernetes necesarios para desplegar Alfresco.
- **Manifiestos de Kubernetes**: Incluye los archivos YAML necesarios para desplegar el operador y los recursos asociados.

## Despliegue del Operador y CRD

Para desplegar el operador y el CRD en tu clúster de Kubernetes, sigue estos pasos:

```bash
git clone https://github.com/cparedesr/operator-crd-alfresco.git
cd operator-crd-alfresco
kubectl apply -f operator-crd-alfresco.yaml
kubectl apply -f almacenamiento.yml
kubectl apply -f alfresco-community.yaml
```

## Comandos de explotación
Para ver el estado tanto de nuestros aplicativos como de nuestro CRD:
```
# Ver el estado de nuestro CRD
kubectl get crd

# Ver el estado del objeto Alfresco que hemos creado
kubectl get alfresco
kubectl describe alfresco alfresco-community

# Ver el estado de todos los aplicativos
kubectl get pods

# En el namespace veremos también un pod que es el que maneja los eventos en nuestro clúster. Si se hiciera alguna modificación en el código de Python y necesitamos depurar:
kubectl logs alfresco-community-operator-XXXXXXXX-XXXXX
kubectl describe pod alfresco-community-operator-XXXXXXXX-XXXXX
```

## Antes de desplegar

1. **Almacenamiento**: 
    - El almacenamiento que se despliega a modo de ejemplo ya que ha sido utilizado durante el desarrollo del controlador con Docker Desktop. Aunque cada proveedor de Kubernetes lo trate de una manera diferente, en nuestro fichero YAML ya viene preparado para configurar cualquier PVC.

    ```
    volumes:
    - name: alfresco-data
        mountPath: /usr/local/tomcat/alf_data
        existingClaim: alfresco-storage-pvc
    ```
    - Por lo tanto, tendremos que tener nuestro almacenamiento correctamente configurado antes de aplicar nuestra aplicación.

2. **Reinicio del Pod de Alfresco**:
Durante el despliegue de nuestro Alfresco, el pod de Alfresco se reinicia una vez, ya que la BBDD también la estamos arrancando en la colección y Alfresco se inicia antes de que la BBDD esté disponible. Si se quiere utilizar una BBDD externa, simplemente eliminar el servicio de Postgres y el reinicio no se producirá.

3. **Servicios**:

El tipo de los servicios es configurable en el fichero YAML de nuestro Alfresco (ClusterIP, NodePort y LoadBalancer). Los servicios de Alfresco, Share y Solr están configurados como NodePort.

4. **Namespace**:
Todos los servicios se despliega en el namespace por default, se peude cambiar perfectamente de namespace en lo ficheros yml, y en la última linea de nuestro fichero de python.

## Próximas versiones del controlador
Implementación del Secret correspondiente para poder descargar imágenes de un repositorio privado. Por el momento, solo se pueden descargar de Docker Hub.

## Ejamplos de funcionalidad
A continuación se detallan algunos ejemplos (no implementados), para aprovechar al máximo nuestro controlador. Aunque dependiendo de cada proyecto podrá tener aplicaciones diferentes:

- Controlar la actualización de Alfresco, para que sea más segura frente a errores humanos.

- Controlar personalizaciones de Alfresco que interactúen con la API de Kubernetes, por ejemplo, el almacenamiento o ficheros temporales.

## Contribuciones
¡Las contribuciones son bienvenidas! Si deseas contribuir a este proyecto, por favor crea un fork del repositorio y envía un pull request con tus cambios.
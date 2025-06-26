module "namenode" {
  source  = "github.com/hoangnam-study/terraform-google-modules//modules/vm/src?ref=v1.0.1"
  vm_name = "namenode"
}

module "datanode1" {
  source  = "github.com/hoangnam-study/terraform-google-modules//modules/vm/src?ref=v1.0.1"
  vm_name = "datanode1"
}

module "datanode2" {
  source  = "github.com/hoangnam-study/terraform-google-modules//modules/vm/src?ref=v1.0.1"
  vm_name = "datanode2"
}

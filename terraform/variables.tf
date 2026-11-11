variable "subscription_id" {
  type        = string
  description = "Your Azure subscription ID"
}

variable "location" {
  type        = string
  description = "Azure region"
  default     = "centralindia"
}

variable "project" {
  type    = string
  default = "campushub"
}

variable "environment" {
  type    = string
  default = "dev"
}
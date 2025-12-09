-- MySQL Workbench Forward Engineering

SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0;
SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0;
SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='ONLY_FULL_GROUP_BY,STRICT_TRANS_TABLES,NO_ZERO_IN_DATE,NO_ZERO_DATE,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';

-- -----------------------------------------------------
-- Schema mydb
-- -----------------------------------------------------

-- -----------------------------------------------------
-- Schema mydb
-- -----------------------------------------------------
CREATE SCHEMA IF NOT EXISTS `mydb` DEFAULT CHARACTER SET utf8 ;
SHOW WARNINGS;
USE `mydb` ;

-- -----------------------------------------------------
-- Table `pedido_cliente`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `pedido_cliente` (
  `idpedido_cliente` INT(11) NOT NULL AUTO_INCREMENT,
  `data` DATE NOT NULL,
  `quantidade` INT(11) NOT NULL,
  PRIMARY KEY (`idpedido_cliente`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `cliente`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `cliente` (
  `idcadastro_cliente` INT(11) NOT NULL,
  `senha` VARCHAR(45) NOT NULL,
  `email` VARCHAR(45) NOT NULL,
  `telefone` VARCHAR(45) NOT NULL,
  `nome` VARCHAR(45) NOT NULL,
  `cep` VARCHAR(8) NOT NULL,
  `pedido_cliente_idpedido_cliente` INT(11) NOT NULL,
  PRIMARY KEY (`idcadastro_cliente`),
  CONSTRAINT `fk_cadastro_cliente_pedido_cliente1`
    FOREIGN KEY (`pedido_cliente_idpedido_cliente`)
    REFERENCES `pedido_cliente` (`idpedido_cliente`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `empilhadeira`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `empilhadeira` (
  `idempilhadeira` INT(11) NOT NULL AUTO_INCREMENT,
  `modelo` VARCHAR(45) NOT NULL,
  `ano_fab` DATE NOT NULL,
  `nome` VARCHAR(45) NOT NULL,
  PRIMARY KEY (`idempilhadeira`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `movimentacao`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `movimentacao` (
  `id_movimentacao` INT(11) NOT NULL AUTO_INCREMENT,
  `tipo ENUM` VARCHAR(45) NOT NULL,
  `data_mov` VARCHAR(45) NOT NULL,
  `quantidade` VARCHAR(45) NOT NULL,
  `id_produto` VARCHAR(45) NOT NULL,
  `id_funcionario` VARCHAR(45) NOT NULL,
  `id_galpao` VARCHAR(45) NOT NULL,
  PRIMARY KEY (`id_movimentacao`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `estoque`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `estoque` (
  `idestoque` INT(11) NOT NULL AUTO_INCREMENT,
  `localizacao` VARCHAR(45) NOT NULL,
  `data_entrada` DATE NOT NULL,
  `movimentacao_id_movimentacao` INT(11) NOT NULL,
  PRIMARY KEY (`idestoque`),
  CONSTRAINT `fk_estoque_movimentacao1`
    FOREIGN KEY (`movimentacao_id_movimentacao`)
    REFERENCES `movimentacao` (`id_movimentacao`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `pedido_fornecedor`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `pedido_fornecedor` (
  `idpedido_fornecedor` INT(11) NOT NULL AUTO_INCREMENT,
  `data_pedido` DATE NOT NULL,
  `quantidade` INT(11) NOT NULL,
  `nome_produto` VARCHAR(45) NOT NULL,
  `metodo_pag` VARCHAR(45) NOT NULL,
  `cep` VARCHAR(8) NOT NULL,
  `data_entrega` DATE NOT NULL,
  `valor_pedido` VARCHAR(45) NOT NULL,
  PRIMARY KEY (`idpedido_fornecedor`))
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `fornecedor`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `fornecedor` (
  `idcadastro_fornecedor` INT(11) NOT NULL AUTO_INCREMENT,
  `senha` VARCHAR(30) NOT NULL,
  `email` VARCHAR(45) NOT NULL,
  `nome` VARCHAR(45) NOT NULL,
  `telefone` VARCHAR(15) NOT NULL,
  `pedido_fornecedor_idpedido_fornecedor` INT(11) NOT NULL,
  PRIMARY KEY (`idcadastro_fornecedor`),
  CONSTRAINT `fk_cadastro_fornecedor_pedido_fornecedor1`
    FOREIGN KEY (`pedido_fornecedor_idpedido_fornecedor`)
    REFERENCES `pedido_fornecedor` (`idpedido_fornecedor`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `produto`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `produto` (
  `produto_id` INT(11) NOT NULL,
  `nome` VARCHAR(45) NULL DEFAULT NULL,
  `valor` VARCHAR(45) NULL DEFAULT NULL,
  `desc_produto` VARCHAR(45) NULL DEFAULT NULL,
  `quantidade` VARCHAR(45) NULL DEFAULT NULL,
  `quantidade_min` INT(11) NULL DEFAULT NULL,
  `quantidade_max` INT(11) NULL DEFAULT NULL,
  `id_galpao` INT(11) NULL DEFAULT NULL,
  `prateleira` VARCHAR(45) NULL DEFAULT NULL,
  `categoria` VARCHAR(45) NULL DEFAULT NULL,
  `estoque_idestoque` INT(11) NOT NULL,
  `movimentacao_id_movimentacao` INT(11) NOT NULL,
  PRIMARY KEY (`produto_id`),
  CONSTRAINT `fk_Produto_estoque1`
    FOREIGN KEY (`estoque_idestoque`)
    REFERENCES `estoque` (`idestoque`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_Produto_movimentacao1`
    FOREIGN KEY (`movimentacao_id_movimentacao`)
    REFERENCES `movimentacao` (`id_movimentacao`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `galpao`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `galpao` (
  `idgalpao` INT(11) NOT NULL AUTO_INCREMENT,
  `cep` VARCHAR(8) NOT NULL,
  `empilhadeira_idempilhadeira` INT(11) NOT NULL,
  `movimentacao_id_movimentacao` INT(11) NOT NULL,
  PRIMARY KEY (`idgalpao`),
  CONSTRAINT `fk_galpao_empilhadeira1`
    FOREIGN KEY (`empilhadeira_idempilhadeira`)
    REFERENCES `empilhadeira` (`idempilhadeira`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_galpao_movimentacao1`
    FOREIGN KEY (`movimentacao_id_movimentacao`)
    REFERENCES `movimentacao` (`id_movimentacao`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `funcionario`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `funcionario` (
  `idcadastro_funcionario` INT(11) NOT NULL AUTO_INCREMENT,
  `senha` VARCHAR(30) NOT NULL,
  `email` VARCHAR(45) NOT NULL,
  `cpf` VARCHAR(45) NOT NULL,
  `cep` VARCHAR(45) NOT NULL,
  `telefone` VARCHAR(11) NOT NULL,
  `nome` VARCHAR(45) NOT NULL,
  `data_nasc` DATE NOT NULL,
  `data_entrada` DATE NOT NULL,
  `Produto_produto_id` INT(11) NOT NULL,
  `galpao_idgalpao` INT(11) NOT NULL,
  `pedido_fornecedor_idpedido_fornecedor` INT(11) NOT NULL,
  `empilhadeira_idempilhadeira` INT(11) NOT NULL,
  `movimentacao_id_movimentacao` INT(11) NOT NULL,
  PRIMARY KEY (`idcadastro_funcionario`),
  CONSTRAINT `fk_cadastro_funcionario_Produto1`
    FOREIGN KEY (`Produto_produto_id`)
    REFERENCES `produto` (`produto_id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_cadastro_funcionario_empilhadeira1`
    FOREIGN KEY (`empilhadeira_idempilhadeira`)
    REFERENCES `empilhadeira` (`idempilhadeira`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_cadastro_funcionario_galpao1`
    FOREIGN KEY (`galpao_idgalpao`)
    REFERENCES `galpao` (`idgalpao`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_cadastro_funcionario_movimentacao1`
    FOREIGN KEY (`movimentacao_id_movimentacao`)
    REFERENCES `movimentacao` (`id_movimentacao`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_cadastro_funcionario_pedido_fornecedor1`
    FOREIGN KEY (`pedido_fornecedor_idpedido_fornecedor`)
    REFERENCES `pedido_fornecedor` (`idpedido_fornecedor`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `item_cliente`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `item_cliente` (
  `idItem_cliente` INT(11) NOT NULL AUTO_INCREMENT,
  `Produto_produto_id` INT(11) NOT NULL,
  `pedido_cliente_idpedido_cliente` INT(11) NOT NULL,
  PRIMARY KEY (`idItem_cliente`),
  CONSTRAINT `fk_Item_cliente_Produto1`
    FOREIGN KEY (`Produto_produto_id`)
    REFERENCES `produto` (`produto_id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_Item_cliente_pedido_cliente1`
    FOREIGN KEY (`pedido_cliente_idpedido_cliente`)
    REFERENCES `pedido_cliente` (`idpedido_cliente`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

-- -----------------------------------------------------
-- Table `item_fornecedor`
-- -----------------------------------------------------
CREATE TABLE IF NOT EXISTS `item_fornecedor` (
  `idItem_fornecedor` INT(11) NOT NULL AUTO_INCREMENT,
  `Produto_produto_id` INT(11) NOT NULL,
  `pedido_fornecedor_idpedido_fornecedor` INT(11) NOT NULL,
  PRIMARY KEY (`idItem_fornecedor`),
  CONSTRAINT `fk_Item_fornecedor_Produto1`
    FOREIGN KEY (`Produto_produto_id`)
    REFERENCES `produto` (`produto_id`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION,
  CONSTRAINT `fk_Item_fornecedor_pedido_fornecedor1`
    FOREIGN KEY (`pedido_fornecedor_idpedido_fornecedor`)
    REFERENCES `pedido_fornecedor` (`idpedido_fornecedor`)
    ON DELETE NO ACTION
    ON UPDATE NO ACTION)
ENGINE = InnoDB
DEFAULT CHARACTER SET = utf8;

SHOW WARNINGS;

SET SQL_MODE=@OLD_SQL_MODE;
SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS;
SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS;

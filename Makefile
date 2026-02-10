NAME        := ioi_testing_image
CONTAINER   := ioi_testing_container

RUN_FLAG    := -p 8000:8000 --privileged

all: run

run:
	@if [ -z "$$(docker images -q $(NAME) 2>/dev/null)" ]; then \
		echo "Image not found, building..."; \
		$(MAKE) build; \
	fi
	@if [ "$$(docker ps -q -f name=$(CONTAINER))" ]; then \
		echo "Container is already running"; \
	else \
		echo "Running container"; \
		docker run --name $(CONTAINER) $(RUN_FLAG) --rm $(NAME); \
	fi

build: clean
	@echo "Building the image"
	@docker build --no-cache -t $(NAME) .

stop:
	@echo "Stopping container (if running)"
	@docker stop $(CONTAINER) 2>/dev/null || true

status:
	@docker ps -f name=$(CONTAINER)

logs:
	@docker logs -f $(CONTAINER) 2>/dev/null || true

clean: stop
	@echo "Removing image (if exists)"
	@docker rmi $(NAME) --force 2>/dev/null || true

re: clean build run

.PHONY: all run build stop status logs clean re
